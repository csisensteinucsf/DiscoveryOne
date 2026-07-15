from __future__ import annotations

from typing import Any

from .integration_settings import provider_value
from .preservation_catalog import hold_field_for_source, source_key

from .system_admin_config import (
    tech_group_ticket_categories,
    ticket_legacy_fields,
    ticket_workflow_lookup,
)
from .system_settings import load_system_settings


def ticket_workflows_raw() -> list[dict[str, Any]]:
    try:
        raw = load_system_settings().get("ticket_workflows") or []
    except Exception:
        return []
    return raw if isinstance(raw, list) else []


def workflow_lookup(*, include_disabled: bool = True) -> dict[str, dict[str, Any]]:
    return ticket_workflow_lookup(ticket_workflows_raw(), include_disabled=include_disabled)


def workflow_categories(*, include_disabled: bool = True) -> set[str]:
    return set(workflow_lookup(include_disabled=include_disabled).keys())


def matched_email_required_categories() -> set[str]:
    return {
        key
        for key, workflow in workflow_lookup(include_disabled=True).items()
        if bool(workflow.get("requires_matched_email"))
    }


def category_hold_fields() -> dict[str, str]:
    fields: dict[str, str] = {}
    for key, workflow in workflow_lookup(include_disabled=True).items():
        hold_key = str(workflow.get("hold_key") or "").strip()
        if hold_key:
            fields[key] = hold_key
    return fields


def category_legacy_fields() -> dict[str, str]:
    return ticket_legacy_fields(ticket_workflows_raw())


def category_label(category: str | None) -> str:
    key = str(category or "").strip()
    if not key:
        return ""
    workflow = workflow_lookup(include_disabled=True).get(key)
    return str((workflow or {}).get("label") or key).strip()


def tech_group_categories() -> dict[str, set[str]]:
    return tech_group_ticket_categories(ticket_workflows_raw())


def approval_workflow_lookup(*, provider: str | None = None) -> dict[str, dict[str, Any]]:
    selected_provider = str(
        provider if provider is not None else provider_value("ticket_provider", default="none")
    ).strip().lower()
    if selected_provider in {"", "none", "manual"}:
        return {}

    return {
        key: workflow
        for key, workflow in workflow_lookup(include_disabled=False).items()
        if bool(
            workflow.get(
                "external_ticket_enabled",
                workflow.get("service_now_enabled", False),
            )
        )
        and bool(workflow.get("auto_create_on_approval"))
    }


def approval_categories_for_custodian(
    custodian: Any,
    *,
    provider: str | None = None,
    workflows: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    categories: list[str] = []
    custom_records = getattr(custodian, "custom_preservation", None) or []
    custom_by_key = {
        source_key(getattr(record, "source_key", None)): record
        for record in custom_records
    }

    for key, workflow in (workflows if workflows is not None else approval_workflow_lookup(provider=provider)).items():
        configured_hold_key = str(workflow.get("hold_key") or "").strip()
        hold_field = configured_hold_key
        if not hold_field or not hasattr(custodian, hold_field):
            hold_field = hold_field_for_source(
                workflow.get("preservation_source") or configured_hold_key or key
            )
        if hold_field and (
            bool(getattr(custodian, hold_field, False))
            or bool(getattr(custodian, f"{hold_field}_pending", False))
        ):
            categories.append(key)
            continue

        custom_key = source_key(
            workflow.get("preservation_source") or configured_hold_key or key
        )
        custom_record = custom_by_key.get(custom_key)
        if custom_record and (
            bool(getattr(custom_record, "active", False))
            or bool(getattr(custom_record, "pending", False))
        ):
            categories.append(key)

    return categories


def completion_satisfies_hold_key(workflow: dict[str, Any] | None) -> str:
    metadata = workflow or {}
    hold_key = str(metadata.get("completion_satisfies_hold_key") or "").strip()
    if hold_key:
        return hold_key
    return hold_field_for_source(metadata.get("completion_satisfies_source"))


def servicenow_category_config() -> dict[str, dict[str, str]]:
    categories: dict[str, dict[str, str]] = {}
    for key, workflow in workflow_lookup(include_disabled=False).items():

        if not workflow.get(
            "external_ticket_enabled",
            workflow.get("service_now_enabled", False),
        ):
            continue
        label = str(workflow.get("label") or key).strip() or key
        categories[key] = {
            "short_description": str(workflow.get("short_description") or label).strip() or label,
            "assignment_group": str(workflow.get("assignment_group") or "").strip(),
            "symptom": str(workflow.get("symptom") or "Inquiry").strip() or "Inquiry",
            "incident_keyword": str(workflow.get("incident_keyword") or "").strip(),
            "request_type": str(workflow.get("request_type") or label).strip() or label,
            "link_label": str(workflow.get("link_label") or "Case link").strip() or "Case link",
            "append_case_name_to_short_description": str(workflow.get("append_case_name_to_short_description") or "").strip(),
        }
    return categories
