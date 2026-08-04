import json
from typing import Any, Optional

from fastapi import HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import case_custodians as custodian_core
from . import models, schemas


def bulk_import_custodians_for_case(
    *,
    case_id: int,
    payload: schemas.CustodianBulkCreateRequest,
    db: Session,
    request: Optional[Request],
    user: models.User,
) -> schemas.CustodianBulkCreateResponse:
    case = custodian_core._load_case_for_custodian_write(case_id, db, user)
    requested = list(payload.custodians or [])
    if not requested:
        return schemas.CustodianBulkCreateResponse()

    from .case_holds import assign_custodians_to_hold

    requested_hold_ids = sorted({int(value) for value in (payload.hold_ids or []) if int(value) > 0})
    if requested_hold_ids:
        active_holds = (
            db.query(models.CaseHold)
            .filter(
                models.CaseHold.case_id == case_id,
                models.CaseHold.id.in_(requested_hold_ids),
                models.CaseHold.status == "active",
            )
            .all()
        )
        found_hold_ids = {int(hold.id) for hold in active_holds}
        missing_hold_ids = sorted(set(requested_hold_ids) - found_hold_ids)
        if missing_hold_ids:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Every selected hold must be an active hold for this case",
                    "hold_ids": missing_hold_ids,
                },
            )
        hold_ids = requested_hold_ids
    else:
        hold_ids = []

    existing_emails = custodian_core._case_custodian_email_set(db, case_id)
    batch_seen: set[str] = set()
    candidate_payloads: list[dict[str, Any]] = []
    duplicate_count = 0
    errors: list[str] = []
    created: list[models.Custodian] = []

    for item in requested:
        data = item.dict()
        custom_preservation = custodian_core._extract_custom_preservation_payload(data)
        email_norm = custodian_core._normalize_email(data.get("email"))
        if email_norm and (email_norm in existing_emails or email_norm in batch_seen):
            duplicate_count += 1
            continue
        if email_norm:
            batch_seen.add(email_norm)
            existing_emails.add(email_norm)
        candidate_payloads.append({**data, "custom_preservation": custom_preservation})

    if candidate_payloads:
        prepared: list[tuple[dict[str, Any], models.Custodian, Any, list[dict[str, Any]]]] = []
        try:
            for data in candidate_payloads:
                data_for_create = dict(data)
                custom_preservation = data_for_create.pop("custom_preservation", [])
                data_for_create.pop("hold_ids", None)
                custodian, _email_norm, _trimmed_email, name_email_review = custodian_core._prepare_custodian_for_create(
                    case_id=case_id,
                    case=case,
                    data=data_for_create,
                    use_ai_review=False,
                )
                prepared.append((data_for_create, custodian, name_email_review, custom_preservation))
                db.add(custodian)
            db.flush()
            for _data, custodian, _review, custom_preservation in prepared:
                custodian_core._sync_custom_preservation(db, custodian, custom_preservation)
                if bool(getattr(custodian, "holds_slack", False)):
                    custodian_core._sync_slack_hold_transition(
                        case,
                        custodian,
                        before_holds_slack=False,
                        before_email=None,
                        db=db,
                        actor_id=user.id,
                        request=request,
                        source="custodian_bulk_import",
                    )
            created_ids = [int(custodian.id) for _data, custodian, _review, _custom in prepared]
            for hold_id in hold_ids:
                assign_custodians_to_hold(
                    db,
                    case_id=case_id,
                    hold_id=hold_id,
                    custodian_ids=created_ids,
                )
            db.commit()
            for _data, custodian, name_email_review, _custom_preservation in prepared:
                db.refresh(custodian)
                if getattr(custodian, "added_at", None) is None:
                    setattr(custodian, "added_at", getattr(custodian, "created_at", None))
                created.append(custodian)
                custodian_core._log_custodian_create_success(
                    db,
                    case_id=case_id,
                    case=case,
                    custodian=custodian,
                    actor_id=getattr(user, "id", None),
                    request=request,
                    name_email_review=name_email_review,
                )
        except IntegrityError as exc:
            db.rollback()
            custodian_core.logger.warning("Bulk custodian import fell back to per-row processing for case %s after integrity error: %s", case_id, exc)
            existing_emails = custodian_core._case_custodian_email_set(db, case_id)
            created = []
            for data in candidate_payloads:
                data_for_create = dict(data)
                custom_preservation = data_for_create.pop("custom_preservation", [])
                data_for_create.pop("hold_ids", None)
                email_norm = custodian_core._normalize_email(data.get("email"))
                if email_norm and email_norm in existing_emails:
                    duplicate_count += 1
                    continue
                try:
                    custodian, email_norm_prepared, _trimmed_email_for_log, name_email_review = custodian_core._prepare_custodian_for_create(
                        case_id=case_id,
                        case=case,
                        data=data_for_create,
                        use_ai_review=False,
                    )
                    db.add(custodian)
                    db.flush()
                    custodian_core._sync_custom_preservation(db, custodian, custom_preservation)
                    if bool(getattr(custodian, "holds_slack", False)):
                        custodian_core._sync_slack_hold_transition(
                            case,
                            custodian,
                            before_holds_slack=False,
                            before_email=None,
                            db=db,
                            actor_id=user.id,
                            request=request,
                            source="custodian_bulk_import_fallback",
                        )
                    for hold_id in hold_ids:
                        assign_custodians_to_hold(
                            db,
                            case_id=case_id,
                            hold_id=hold_id,
                            custodian_ids=[int(custodian.id)],
                        )
                    db.commit()
                    db.refresh(custodian)
                    if getattr(custodian, "added_at", None) is None:
                        setattr(custodian, "added_at", getattr(custodian, "created_at", None))
                    created.append(custodian)
                    if email_norm_prepared:
                        existing_emails.add(email_norm_prepared)
                    custodian_core._log_custodian_create_success(
                        db,
                        case_id=case_id,
                        case=case,
                        custodian=custodian,
                        actor_id=getattr(user, "id", None),
                        request=request,
                        name_email_review=name_email_review,
                    )
                except IntegrityError as row_exc:
                    db.rollback()
                    if email_norm and custodian_core._email_in_use(db, case_id, email_norm):
                        duplicate_count += 1
                        continue
                    custodian_core._log_custodian_create_failure(
                        db,
                        case_id=case_id,
                        case=case,
                        actor_id=getattr(user, "id", None),
                        request=request,
                        custodian_name=data.get("name"),
                        custodian_email=(data.get("email") or "").strip() or None,
                        error="integrity_error",
                        status_code=500,
                    )
                    custodian_core.logger.error("Failed to import custodian for case %s: %s", case_id, row_exc)
                    errors.append("Unable to add custodian")
                except Exception as row_exc:
                    db.rollback()
                    detail_value = getattr(row_exc, "detail", None)
                    if isinstance(detail_value, (dict, list)):
                        detail_text = json.dumps(detail_value)
                    elif detail_value is not None:
                        detail_text = str(detail_value)
                    else:
                        detail_text = str(row_exc)
                    custodian_core._log_custodian_create_failure(
                        db,
                        case_id=case_id,
                        case=case,
                        actor_id=getattr(user, "id", None),
                        request=request,
                        custodian_name=data.get("name"),
                        custodian_email=(data.get("email") or "").strip() or None,
                        error=detail_text,
                        status_code=int(getattr(row_exc, "status_code", 500) or 500),
                    )
                    custodian_core.logger.error("Failed to import custodian for case %s: %s", case_id, row_exc)
                    errors.append(detail_text or "Unable to add custodian")
        except Exception as exc:
            db.rollback()
            custodian_core.logger.error("Failed bulk custodian import for case %s: %s", case_id, exc)
            raise HTTPException(status_code=500, detail="Unable to import custodians")

    custodian_core._bulk_import_log_summary(
        db,
        case_id=case_id,
        case=case,
        actor_id=getattr(user, "id", None),
        request=request,
        requested_count=len(requested),
        created_count=len(created),
        duplicate_count=duplicate_count,
        failed_count=len(errors),
        used_ai_review=False,
    )
    return schemas.CustodianBulkCreateResponse(
        created=custodian_core._custodian_read_many(db, created),
        created_count=len(created),
        duplicate_count=duplicate_count,
        failed_count=len(errors),
        errors=errors,
    )

