from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import urlparse

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from . import models
from .audit import log_event
from .auth import current_user as get_current_user, current_user_optional as get_current_user_optional
from .database import get_db
from .emailer import mail_provider_ready, send_email
from .integration_settings import (
    MASKED_SECRET_VALUE,
    encrypt_secret,
    validate_integration_settings,
)
from .permissions import is_sys_admin
from .integration_policy import (
    merge_enabled_integrations,
    merge_integration_configs,
    merge_provider_settings,
    reconcile_provider_enablement,
    provider_options,
)
from .safe_log import debug_suppressed as _debug_suppressed
from .system_admin_config import (
    THEMES,
    AccountReviewPayload,
    BrandingTextPayload,
    CaseClosurePayload,
    CaseNamingPayload,
    CaseStatusPayload,
    CaseRequestSettingsPayload,
    DeploymentPayload,
    EmailTestPayload,
    InstitutionSettingsPayload,
    NTPConfigPayload,
    NotificationsPayload,
    PreservationSourcesPayload,
    SMTPConfigPayload,
    SystemIntegrationsPayload,
    TicketWorkflowsPayload,
    normalize_case_naming,
    normalize_institution_config,
    normalize_preservation_sources,
    normalize_ticket_workflows,
    public_institution_config,
    public_branding_config,
    public_account_review_config,
    public_case_closure_config,
    public_case_status_config,
    public_case_request_settings_config,
    public_consent_notification_config,
    public_deployment_config,
    normalize_deployment_config,
    public_integration_admin_config,
    public_integration_config_summary,
    public_logo_url,
    public_notifications_config,
    public_ntp_config,
    public_smtp_config,
    public_ticket_workflows,
)
from .system_settings import load_system_settings, save_system_settings

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/system/settings", tags=["system"])
def sys_get_settings(actor: Optional[models.User] = Depends(get_current_user_optional)):
    s = load_system_settings()
    is_admin = is_sys_admin(actor)
    active_logo_id = s.get("active_logo")
    active_logo_url = None
    for logo in s.get("logos", []):
        if logo.get("id") == active_logo_id:
            active_logo_url = public_logo_url(logo.get("filename"))
    user_theme = "light"
    if actor:
        user_theme = getattr(actor, "user_theme", None) or user_theme
    else:
        user_theme = s.get("user_theme") or user_theme
    payload = {
        "active_theme": s.get("active_theme") or "light",
        "themes": THEMES,
        "user_theme": user_theme,
        "logos": [
            {"id": logo["id"], "filename": logo["filename"], "url": public_logo_url(logo["filename"])}
            for logo in s.get("logos", [])
        ],
        "active_logo_id": active_logo_id,
        "active_logo_url": active_logo_url,
        "branding": public_branding_config(s.get("branding")),
        "deployment": public_deployment_config(s.get("deployment")),
        "app_name": public_branding_config(s.get("branding")).get("app_name"),
        "app_tagline": public_branding_config(s.get("branding")).get("app_tagline"),
        "institution": public_institution_config(include_exceptions=is_admin),
        "integrations": public_integration_admin_config() if is_admin else public_integration_config_summary(),
        "preservation_sources": normalize_preservation_sources(s.get("preservation_sources")),
        "ticket_workflows": public_ticket_workflows(s.get("ticket_workflows")),
        "case_naming": normalize_case_naming(s.get("case_naming")),
        "case_closure": public_case_closure_config(s.get("case_closure")),
        "case_status": public_case_status_config(s.get("case_status")),
        "case_requests": public_case_request_settings_config(s.get("case_requests")),
    }
    payload["smtp"] = public_smtp_config(s.get("smtp")) if is_admin else None
    payload["notifications"] = public_notifications_config(s.get("notifications"), include_webhook=is_admin) if is_admin else None
    payload["ntp"] = public_ntp_config(s.get("ntp")) if is_admin else None
    payload["account_review"] = public_account_review_config(s.get("account_review")) if is_admin else None
    return payload


def _public_integration_admin_payload() -> dict[str, Any]:
    payload = public_integration_admin_config()
    payload["provider_options"] = {
        key: sorted(values)
        for key, values in provider_options().items()
    }
    return payload


@router.get("/system/institution", tags=["system"])
def sys_get_institution(actor: models.User = Depends(get_current_user)):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return {"institution": public_institution_config(include_exceptions=True)}


@router.post("/system/institution", tags=["system"])
def sys_update_institution(
    payload: InstitutionSettingsPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    try:
        normalized = normalize_institution_config(payload.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    settings = load_system_settings()
    settings["institution"] = normalized
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_institution_update",
            actor_id=actor.id,
            target_type="system",
            details={
                "org_name": normalized.get("org_name"),
                "allowed_requestor_email_domains": normalized.get("allowed_requestor_email_domains"),
                "requestor_email_exception_count": len(normalized.get("requestor_email_exceptions") or []),
            },
            request=request,
        )
    except Exception:
        db.rollback()
    return {"institution": public_institution_config(include_exceptions=True)}


@router.get("/system/integrations", tags=["system"])
def sys_get_integrations(actor: models.User = Depends(get_current_user)):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return _public_integration_admin_payload()


@router.post("/system/deployment", tags=["system"])
def sys_update_deployment(
    payload: DeploymentPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    try:
        normalized = normalize_deployment_config(payload.dict(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    settings = load_system_settings()
    deployment = settings.get("deployment") if isinstance(settings.get("deployment"), dict) else {}
    tls = deployment.get("tls") if isinstance(deployment.get("tls"), dict) else {}
    deployment.update(normalized)
    deployment["tls"] = tls
    settings["deployment"] = deployment
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_deployment_update",
            actor_id=actor.id,
            target_type="system",
            details=normalized,
            request=request,
        )
    except Exception:
        db.rollback()
    return {"deployment": public_deployment_config(settings.get("deployment"))}


@router.post("/system/branding/text", tags=["system"])
def sys_update_branding_text(
    payload: BrandingTextPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    app_name = (payload.app_name or "").strip()[:80] or "DiscoveryOne"
    app_tagline = (payload.app_tagline or "").strip()[:140]
    settings = load_system_settings()
    settings["branding"] = {"app_name": app_name, "app_tagline": app_tagline}
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_branding_text_update",
            actor_id=actor.id,
            target_type="system",
            details={"app_name": app_name, "app_tagline_set": bool(app_tagline)},
            request=request,
        )
    except Exception:
        db.rollback()
    return {"ok": True, "branding": public_branding_config(settings.get("branding"))}


@router.post("/system/preservation_sources", tags=["system"])
def sys_update_preservation_sources(
    payload: PreservationSourcesPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    settings = load_system_settings()
    sources = normalize_preservation_sources(payload.preservation_sources)
    settings["preservation_sources"] = sources
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_preservation_sources_update",
            actor_id=actor.id,
            target_type="system",
            details={
                "enabled_sources": [item["key"] for item in sources if item.get("enabled")],
                "custom_sources": [item["key"] for item in sources if not item.get("built_in")],
            },
            request=request,
        )
    except Exception:
        db.rollback()
    return {"preservation_sources": sources}


@router.post("/system/ticket_workflows", tags=["system"])
def sys_update_ticket_workflows(
    payload: TicketWorkflowsPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    settings = load_system_settings()
    workflows = normalize_ticket_workflows(payload.ticket_workflows)
    settings["ticket_workflows"] = workflows
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_ticket_workflows_update",
            actor_id=actor.id,
            target_type="system",
            details={
                "enabled_workflows": [item["key"] for item in workflows if item.get("enabled")],
                "tech_groups": sorted({item.get("tech_group") for item in workflows if item.get("tech_group")}),
            },
            request=request,
        )
    except Exception:
        db.rollback()
    return {"ticket_workflows": public_ticket_workflows(workflows)}

@router.post("/system/case_naming", tags=["system"])
def sys_update_case_naming(
    payload: CaseNamingPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    try:
        normalized = normalize_case_naming({"mode": payload.mode}, strict=True)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    settings = load_system_settings()
    settings["case_naming"] = normalized
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_case_naming_update",
            actor_id=actor.id,
            target_type="system",
            details=normalized,
            request=request,
        )
    except Exception:
        db.rollback()
    return {"case_naming": normalized}


@router.post("/system/case_closure", tags=["system"])
def sys_update_case_closure(
    payload: CaseClosurePayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    normalized = public_case_closure_config(payload.dict(exclude_none=True))
    settings = load_system_settings()
    settings["case_closure"] = normalized
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_case_closure_update",
            actor_id=actor.id,
            target_type="system",
            details=normalized,
            request=request,
        )
    except Exception:
        db.rollback()
    return {"case_closure": normalized}


@router.post("/system/case_requests", tags=["system"])
def sys_update_case_request_settings(
    payload: CaseRequestSettingsPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    settings = load_system_settings()
    existing = settings.get("case_requests") if isinstance(settings.get("case_requests"), dict) else {}
    incoming = payload.dict(exclude_none=True)
    normalized = public_case_request_settings_config({**existing, **incoming})
    settings["case_requests"] = normalized
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_case_request_settings_update",
            actor_id=actor.id,
            target_type="system",
            details=normalized,
            request=request,
        )
    except Exception:
        db.rollback()
    return {"case_requests": normalized}


@router.post("/system/case_status", tags=["system"])
def sys_update_case_status(
    payload: CaseStatusPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    normalized = public_case_status_config(payload.dict(exclude_none=True))
    settings = load_system_settings()
    settings["case_status"] = normalized
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_case_status_update",
            actor_id=actor.id,
            target_type="system",
            details=normalized,
            request=request,
        )
    except Exception:
        db.rollback()
    return {"case_status": normalized}


@router.post("/system/integrations", tags=["system"])
def sys_update_integrations(
    payload: SystemIntegrationsPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")

    settings = load_system_settings()
    enabled = merge_enabled_integrations(
        settings.get("enabled_integrations"),
        payload.enabled_integrations,
    )
    settings["enabled_integrations"] = enabled

    providers = merge_provider_settings(
        settings.get("integrations"),
        payload.providers,
        reject_unsupported=False,
    )
    settings["integrations"] = providers

    enabled = reconcile_provider_enablement(
        enabled,
        providers,
        changed_provider_fields=set((payload.providers or {}).keys()),
    )
    settings["enabled_integrations"] = enabled

    configs = merge_integration_configs(
        settings.get("integration_configs"),
        payload.configs,
    )
    settings["integration_configs"] = configs

    try:
        validate_integration_settings(
            enabled_integrations=settings.get("enabled_integrations") or {},
            providers=settings.get("integrations") or {},
            configs=settings.get("integration_configs") or {},
            smtp=settings.get("smtp") or {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_integrations_update",
            actor_id=actor.id,
            target_type="system",
            details={
                "enabled_integrations": sorted([k for k, v in enabled.items() if v]),
                "providers": providers,
                "configured_sections": sorted([k for k, v in configs.items() if isinstance(v, dict) and v]),
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_admin.py:system_integrations_update", exc)
    return _public_integration_admin_payload()


@router.post("/system/account_review", tags=["system"])
def sys_update_account_review(
    payload: AccountReviewPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    settings = load_system_settings()
    existing = settings.get("account_review") if isinstance(settings.get("account_review"), dict) else {}
    incoming = payload.dict(exclude_none=True)
    normalized = public_account_review_config({**existing, **incoming})
    settings["account_review"] = normalized
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_account_review_update",
            actor_id=actor.id,
            target_type="system",
            details={k: v for k, v in normalized.items() if k != "last_sent_at"},
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_admin.py:system_account_review_update", exc)
    return {"account_review": normalized}


@router.get("/system/notifications", tags=["system"])
def sys_get_notifications(actor: models.User = Depends(get_current_user)):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    settings = load_system_settings()
    return public_notifications_config(settings.get("notifications"), include_webhook=True)


def _notification_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _merge_search_delivery_reminder_settings(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    current = existing.get("search_delivery_reminders") if isinstance(existing.get("search_delivery_reminders"), dict) else {}
    new = incoming.get("search_delivery_reminders") if isinstance(incoming.get("search_delivery_reminders"), dict) else {}
    merged = {**current, **new}
    return {
        "enabled": bool(merged.get("enabled", True)),
        "interval_days": _notification_int(merged.get("interval_days"), 7, minimum=1, maximum=365),
        "loop_seconds": _notification_int(merged.get("loop_seconds"), 3600, minimum=300, maximum=86400),
        "batch_size": _notification_int(merged.get("batch_size"), 25, minimum=1, maximum=500),
    }


def _merge_consent_notification_settings(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    current = existing.get("consent_notifications") if isinstance(existing.get("consent_notifications"), dict) else {}
    new = incoming.get("consent_notifications") if isinstance(incoming.get("consent_notifications"), dict) else {}
    return public_consent_notification_config({**current, **new})


def _merge_notifications(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    def merge_channel(channel_name: str, fields: tuple[str, ...]) -> Dict[str, Any]:
        current = existing.get(channel_name) if isinstance(existing.get(channel_name), dict) else {}
        new = incoming.get(channel_name) if isinstance(incoming.get(channel_name), dict) else {}
        merged_events: Dict[str, Dict[str, Any]] = {}
        current_events = current.get("events") if isinstance(current.get("events"), dict) else {}
        incoming_events = new.get("events") if isinstance(new.get("events"), dict) else {}
        for key, meta in current_events.items():
            current_meta = meta if isinstance(meta, dict) else {}
            incoming_meta = incoming_events.get(key) if isinstance(incoming_events.get(key), dict) else {}
            merged = dict(current_meta)
            merged["enabled"] = bool(incoming_meta.get("enabled", current_meta.get("enabled", True)))
            for field in fields:
                if field in incoming_meta:
                    merged[field] = (incoming_meta.get(field) or "").strip()
            merged_events[key] = merged
        for key, meta in incoming_events.items():
            if key in merged_events or not isinstance(meta, dict):
                continue
            merged = {"enabled": bool(meta.get("enabled", True))}
            for field in fields:
                merged[field] = (meta.get(field) or "").strip()
            merged_events[key] = merged
        out = {"events": merged_events or current_events}
        if channel_name == "teams":
            current_webhook = str(current.get("webhook_url") or "").strip()
            incoming_webhook = str(new.get("webhook_url") or "").strip()
            if bool(new.get("clear_webhook")):
                out["webhook_url"] = ""
            elif incoming_webhook and incoming_webhook != MASKED_SECRET_VALUE:
                parsed = urlparse(incoming_webhook)
                if parsed.scheme.lower() != "https" or not parsed.netloc:
                    raise HTTPException(status_code=422, detail="Teams webhook URL must be a valid HTTPS URL")
                out["webhook_url"] = encrypt_secret(incoming_webhook)
            else:
                out["webhook_url"] = encrypt_secret(current_webhook)
        return out

    return {
        "teams": merge_channel("teams", ("template",)),
        "email": merge_channel("email", ("subject", "body")),
        "search_delivery_reminders": _merge_search_delivery_reminder_settings(existing, incoming),
        "consent_notifications": _merge_consent_notification_settings(existing, incoming),
    }

@router.post("/system/notifications", tags=["system"])
def sys_update_notifications(
    payload: NotificationsPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    settings = load_system_settings()
    existing = settings.get("notifications") or {}
    incoming = payload.dict(exclude_none=True)
    merged = _merge_notifications(existing, incoming)
    if merged.get("teams", {}).get("webhook_url") is None:
        merged["teams"]["webhook_url"] = ""
    for meta in merged.get("teams", {}).get("events", {}).values():
        template = (meta.get("template") or "").strip()
        meta["template"] = template[:5000]
    for meta in merged.get("email", {}).get("events", {}).values():
        subject = (meta.get("subject") or "").strip()
        body = (meta.get("body") or "").strip()
        meta["subject"] = subject[:500]
        meta["body"] = body[:10000]
    settings["notifications"] = merged
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_notifications_update",
            target_type="system",
            actor_id=actor.id,
            details={
                "teams_events": list((merged.get("teams") or {}).get("events", {}).keys()),
                "email_events": list((merged.get("email") or {}).get("events", {}).keys()),
                "search_delivery_reminders": merged.get("search_delivery_reminders") or {},
                "consent_notifications": merged.get("consent_notifications") or {},
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_admin.py:system_notifications_update", exc)
    return public_notifications_config(settings.get("notifications"), include_webhook=True)


@router.post("/system/theme", tags=["system"])
def sys_set_theme(
    payload: dict = Body(...),
    actor: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    theme_raw = (payload or {}).get("theme") or (payload or {}).get("user_theme")
    theme = (theme_raw or "").strip().lower()
    if theme not in {"light", "dark", "system"}:
        raise HTTPException(status_code=422, detail="theme must be light, dark, or system")
    try:
        actor.user_theme = theme
        db.add(actor)
        db.commit()
        db.refresh(actor)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Unable to update theme") from exc
    try:
        log_event(
            db,
            action="user_theme_update",
            target_type="user",
            target_id=actor.id,
            user_id=actor.id,
            details={"theme": theme},
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_admin.py:user_theme_update", exc)
    return {"ok": True, "theme": theme, "user_theme": theme}


@router.post("/system/case_sort", tags=["system"])
def sys_set_case_sort(
    payload: dict = Body(...),
    actor: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raw = (payload or {}).get("case_sort_mode") or (payload or {}).get("case_sort") or (payload or {}).get("mode")
    mode = (raw or "").strip().lower()
    if mode in {"ediscovery_case_name", "case_name", "name", "ediscovery"}:
        mode = "ediscovery"
    if mode in {"legal_case_name", "legal"}:
        mode = "legal"
    if mode not in {"ediscovery", "legal"}:
        raise HTTPException(status_code=422, detail="case_sort_mode must be ediscovery or legal")
    try:
        actor.case_sort_mode = mode
        db.add(actor)
        db.commit()
        db.refresh(actor)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Unable to update case sort preference") from exc
    try:
        log_event(
            db,
            action="user_case_sort_update",
            target_type="user",
            target_id=actor.id,
            actor_id=actor.id,
            details={"case_sort_mode": mode},
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_admin.py:user_case_sort_update", exc)
    return {"ok": True, "case_sort_mode": mode}


@router.post("/system/email/test", tags=["system"])
def sys_send_test_email(
    payload: EmailTestPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    if not mail_provider_ready():
        raise HTTPException(status_code=400, detail="Mail provider is not configured")
    subject = payload.subject or "DiscoveryOne test email"
    body = payload.body or (
        "This is a connectivity test sent from the eDiscovery system.\n"
        "If you received it, the configured mail provider is working correctly."
    )
    send_email(
        recipients=[payload.to],
        subject=subject,
        body=body,
    )
    try:
        log_event(
            db,
            action="email_test",
            target_type="email",
            actor_id=actor.id,
            details={"to": payload.to},
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_admin.py:email_test", exc)
    return {"ok": True, "to": payload.to}


@router.get("/system/smtp", tags=["system"])
def sys_get_smtp(actor: models.User = Depends(get_current_user)):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    settings = load_system_settings()
    return public_smtp_config(settings.get("smtp"))


@router.post("/system/smtp", tags=["system"])
def sys_update_smtp(
    payload: SMTPConfigPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    host = payload.host.strip()
    if not host:
        raise HTTPException(status_code=422, detail="SMTP host is required")
    from_addr = payload.from_address.strip()
    if not from_addr:
        raise HTTPException(status_code=422, detail="From address is required")
    port = max(1, payload.port or 587)
    settings = load_system_settings()
    smtp = settings.get("smtp") or {}
    username = (payload.username or "").strip()
    incoming_password = (payload.password or "").strip()
    if not username:
        stored_password = None
    elif incoming_password and incoming_password != MASKED_SECRET_VALUE:
        stored_password = encrypt_secret(incoming_password)
    else:
        stored_password = smtp.get("password")
    use_ssl = bool(payload.use_ssl)
    use_tls = bool(payload.use_tls) and not use_ssl
    timeout_seconds = max(1.0, min(300.0, float(payload.timeout_seconds or 15)))
    smtp.update(
        {
            "host": host,
            "port": port,
            "from_address": from_addr,
            "username": username,
            "use_tls": use_tls,
            "use_ssl": use_ssl,
            "timeout_seconds": timeout_seconds,
            "password": stored_password,
        }
    )
    settings["smtp"] = smtp
    try:
        validate_integration_settings(
            enabled_integrations=settings.get("enabled_integrations") or {},
            providers=settings.get("integrations") or {},
            configs=settings.get("integration_configs") or {},
            smtp=smtp,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_smtp_update",
            actor_id=actor.id,
            target_type="system",
            details={
                "host": host,
                "port": port,
                "from_address": from_addr,
                "auth_mode": "username_password" if username and stored_password else "anonymous_or_ip_allowlist",
                "use_tls": use_tls,
                "use_ssl": use_ssl,
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_admin.py:system_smtp_update", exc)
    return {"ok": True, "smtp": public_smtp_config(smtp)}


def _bounded_int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _normalize_ntp_email_csv(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        addr = item.strip().lower()
        if not addr:
            continue
        try:
            normalized = validate_email(
                addr,
                allow_smtputf8=False,
                check_deliverability=False,
            ).normalized.lower()
        except EmailNotValidError as exc:
            raise HTTPException(status_code=422, detail=f"Reserved archive BCC address is invalid: {addr}") from exc
        if normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)
    return ",".join(cleaned)


def _normalize_optional_https_url(value: Any, *, field_label: str) -> str:
    text = str(value or "").strip()[:2048]
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(status_code=422, detail=f"{field_label} must be an https:// URL")
    if parsed.username or parsed.password:
        raise HTTPException(status_code=422, detail=f"{field_label} must not include embedded credentials")
    return text


@router.get("/system/ntp", tags=["system"])
def sys_get_ntp(actor: models.User = Depends(get_current_user)):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    settings = load_system_settings()
    return public_ntp_config(settings.get("ntp"))


@router.post("/system/ntp", tags=["system"])
def sys_update_ntp(
    payload: NTPConfigPayload,
    actor: models.User = Depends(get_current_user),
    request: Request = None,
    db: Session = Depends(get_db),
):
    if not is_sys_admin(actor):
        raise HTTPException(status_code=403, detail="Admin privileges required")
    archive_bcc_address = (str(payload.archive_bcc_address or "")).strip().lower()
    if archive_bcc_address:
        try:
            archive_bcc_address = validate_email(
                archive_bcc_address,
                allow_smtputf8=False,
                check_deliverability=False,
            ).normalized.lower()
        except EmailNotValidError as exc:
            raise HTTPException(status_code=422, detail="Archive BCC address must be a valid email address") from exc
    settings = load_system_settings()
    ntp = settings.get("ntp") or {}
    ack_secret = str(payload.ack_automate_secret or "").strip()
    if ack_secret and ack_secret != MASKED_SECRET_VALUE:
        ntp["ack_automate_secret"] = encrypt_secret(ack_secret)
    ntp.update({
        "archive_bcc_address": archive_bcc_address,
        "archive_copy_required": bool(payload.archive_copy_required),
        "reserved_archive_bcc_addresses": _normalize_ntp_email_csv(payload.reserved_archive_bcc_addresses),
        "ack_automate_url": _normalize_optional_https_url(payload.ack_automate_url, field_label="Acknowledgement bridge URL"),
        "ack_display_url": _normalize_optional_https_url(payload.ack_display_url, field_label="Acknowledgement display URL"),
        "reminder_interval_days": _bounded_int(payload.reminder_interval_days, 14, minimum=1, maximum=365),
        "reminder_duration_days": _bounded_int(payload.reminder_duration_days, 90, minimum=1, maximum=3650),
        "reminder_loop_seconds": _bounded_int(payload.reminder_loop_seconds, 900, minimum=30, maximum=86400),
    })
    settings["ntp"] = ntp
    save_system_settings(settings)
    try:
        log_event(
            db,
            action="system_ntp_update",
            actor_id=actor.id,
            target_type="system",
            details={
                "archive_bcc_address": archive_bcc_address,
                "archive_copy_required": ntp.get("archive_copy_required"),
                "reserved_archive_bcc_addresses": ntp.get("reserved_archive_bcc_addresses"),
                "ack_automate_url_configured": bool(ntp.get("ack_automate_url")),
                "ack_display_url_configured": bool(ntp.get("ack_display_url")),
                "ack_automate_secret_configured": bool(ntp.get("ack_automate_secret")),
                "reminder_interval_days": ntp.get("reminder_interval_days"),
                "reminder_duration_days": ntp.get("reminder_duration_days"),
                "reminder_loop_seconds": ntp.get("reminder_loop_seconds"),
            },
            request=request,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in system_admin.py:system_ntp_update", exc)
    return {"ok": True, "ntp": public_ntp_config(ntp)}

