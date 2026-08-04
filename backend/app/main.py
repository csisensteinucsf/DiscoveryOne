import os
import json
import hashlib
import logging
import secrets
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import APIRouter, Depends, FastAPI, Response, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from .middleware import (
    AuthTokenRateLimitMiddleware,
    CSRFMiddleware,
    ExpensiveEndpointRateLimitMiddleware,
)
from sqlalchemy import bindparam, text, func
from datetime import datetime, timedelta, timezone

from .database import SessionLocal, engine
from .models import Base, Case, CaseConsent, CaseNote, CaseRequestConsentProof, Custodian, NTPTemplate
from .case_naming import suggest_case_name as _suggest_impl
from .auth import current_user, require_admin
from .custodian_guard import install_custodian_guard
from .case_requests import sync_case_request_attachment_bytes, start_case_request_cleanup, start_custodian_lookup_bootstrap
from .db_maintenance import start_db_maintenance_scheduler
from .mw_login_audit import LoginAuditMiddleware  # add near other imports
from .logging_setup import setup_file_logging
from .backups import start_backup_scheduler, notify_missing_backup_key
from .log_shipping import start_log_ship_scheduler
from .file_security import check_upload_scanner_ready
from .runtime_paths import runtime_file
from .system_settings import load_system_settings, save_system_settings
from .ai_assistant import router as ai_assistant_router
from .safe_log import debug_suppressed as _debug_suppressed
try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    _PROMETHEUS_CLIENT_AVAILABLE = True
except Exception:
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    generate_latest = None
    _PROMETHEUS_CLIENT_AVAILABLE = False

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None


install_custodian_guard()

ADMIN_SEED_USERNAME = (os.getenv("ADMIN_SEED_USERNAME") or os.getenv("ADMIN_USERNAME") or "").strip()
ADMIN_SEED_PASSWORD = (os.getenv("ADMIN_SEED_PASSWORD") or os.getenv("ADMIN_PASSWORD") or "").strip()
ADMIN_SEED_FORCE_RESET = os.getenv("ADMIN_SEED_FORCE_RESET", "").strip().lower() in {"1", "true", "yes", "on"}
ADMIN_SEED_STATE_PATH = Path(os.getenv("ADMIN_SEED_STATE_PATH", "/app/data/.admin_seed_state.json"))
ENABLE_SCHEDULERS = (os.getenv("ENABLE_SCHEDULERS") or "1").strip().lower() in {"1", "true", "yes", "on"}
REQUIRE_SCHEDULER_LOCK = (os.getenv("REQUIRE_SCHEDULER_LOCK") or "1").strip().lower() in {"1", "true", "yes", "on"}
SCHEDULER_LOCK_FILE = os.getenv("SCHEDULER_LOCK_FILE", runtime_file("ediscovery_schedulers.lock"))
_scheduler_lock_fd = None
HEALTHCHECK_SECRET = (os.getenv("HEALTHCHECK_SECRET") or "").strip()
ALLOW_INSECURE_DEV = (os.getenv("ALLOW_INSECURE_DEV") or "").strip().lower() in {"1", "true", "yes", "on"}
ALLOW_PARTIAL_STARTUP = (os.getenv("ALLOW_PARTIAL_STARTUP") or "").strip().lower() in {"1", "true", "yes", "on"}
_rate_limits_raw = os.getenv("RATE_LIMITS_ENABLED")
if _rate_limits_raw is None:
    # Backwards-compatible flag name used in .env.example
    _rate_limits_raw = os.getenv("RATE_LIMITS")
RATE_LIMITS_ENABLED = (_rate_limits_raw or "1").strip().lower() in {"1", "true", "yes", "on"}
if not HEALTHCHECK_SECRET and not ALLOW_INSECURE_DEV:
    print("[health] WARNING: HEALTHCHECK_SECRET not set; health endpoints will allow only loopback. Set a secret in production.")

def _is_placeholder_secret(value: str) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return True
    placeholders = {
        "please-change-this",
        "change-me",
        "changeme",
        "password",
        "secret",
        "secret_key",
        "admin",
        "please-set-a-strong-password",
    }
    if normalized in placeholders:
        return True
    if normalized.startswith("please-") and "set" in normalized:
        return True
    return False

if ADMIN_SEED_PASSWORD and not ALLOW_INSECURE_DEV:
    if _is_placeholder_secret(ADMIN_SEED_PASSWORD) or len(ADMIN_SEED_PASSWORD) < 12:
        print("[seed] admin skipped: ADMIN_SEED_PASSWORD appears insecure; set a strong password or ALLOW_INSECURE_DEV=1")
        ADMIN_SEED_PASSWORD = ""  # nosec B105


def _acquire_scheduler_lock() -> bool:
    """Guard to prevent duplicated schedulers across workers."""
    global _scheduler_lock_fd
    path = (SCHEDULER_LOCK_FILE or "").strip()
    if not path:
        return not REQUIRE_SCHEDULER_LOCK
    if fcntl is None:
        if REQUIRE_SCHEDULER_LOCK:
            print("[startup] scheduler lock unavailable (fcntl missing); skipping background jobs")
            return False
        return True
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        if REQUIRE_SCHEDULER_LOCK:
            print(f"[startup] scheduler lock file unavailable: {exc}; skipping background jobs")
            return False
        return True
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _scheduler_lock_fd = fd
        return True
    except (BlockingIOError, OSError):
        try:
            os.close(fd)
        except Exception as exc:
            _debug_suppressed("suppressed exception in main.py:118", exc)
        return False


def _admin_seed_digest(username: str, password: str) -> Optional[str]:
    username = (username or "").strip()
    password = (password or "").strip()
    if not username or not password:
        return None
    raw = f"{username}:{password}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_admin_seed_state() -> dict:
    try:
        data = json.loads(ADMIN_SEED_STATE_PATH.read_text())
        if isinstance(data, dict):
            return data
    except Exception as exc:
        _debug_suppressed("suppressed exception in main.py:137", exc)
    return {}


def _store_admin_seed_state(digest: Optional[str]) -> None:
    if not digest:
        return
    try:
        ADMIN_SEED_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        ADMIN_SEED_STATE_PATH.write_text(json.dumps({"digest": digest}))
    except Exception as exc:
        _debug_suppressed("suppressed exception in main.py:148", exc)

from .startup_schema_bootstrap import run_startup_schema_bootstrap
from .startup_maintenance import run_startup_backfills_once, run_startup_maintenance_once

run_startup_schema_bootstrap()

run_startup_backfills_once()
run_startup_maintenance_once()

# Seed admin user if credentials provided (uses your existing bcrypt hasher)
try:
    from .security import hash_password as _hash
    from sqlalchemy import text as _sql
    _seed_digest = _admin_seed_digest(ADMIN_SEED_USERNAME, ADMIN_SEED_PASSWORD)
    _seed_state = _load_admin_seed_state()
    _seed_already_applied = bool(_seed_digest and _seed_state.get("digest") == _seed_digest)
    if not ADMIN_SEED_USERNAME or not ADMIN_SEED_PASSWORD:
        print("[seed] admin skipped: ADMIN_SEED_USERNAME and ADMIN_SEED_PASSWORD must be set")
    else:
        with engine.begin() as _conn:
            _conn.execute(_sql("""
                UPDATE users
                   SET role = 'sys_admin',
                       is_admin = TRUE
                 WHERE lower(username)=lower(:u)
                   AND (role IS NULL OR role = '')
            """), {"u": ADMIN_SEED_USERNAME})
            exists = _conn.execute(_sql(
                "SELECT 1 FROM users WHERE lower(username)=lower(:u) LIMIT 1"
            ), {"u": ADMIN_SEED_USERNAME}).scalar()
            if not exists:
                _conn.execute(_sql(
                    "INSERT INTO users (username, password_hash, is_admin, email, role) VALUES (:u, :p, TRUE, NULL, 'sys_admin')"
                ), {"u": ADMIN_SEED_USERNAME, "p": _hash(ADMIN_SEED_PASSWORD)})
                print(f"[seed] created admin '{ADMIN_SEED_USERNAME}'")
                _store_admin_seed_state(_seed_digest)
            else:
                if ADMIN_SEED_FORCE_RESET:
                    if _seed_already_applied:
                        print(f"[seed] admin '{ADMIN_SEED_USERNAME}' reset previously applied; skipping")
                    else:
                        _conn.execute(_sql(
                            "UPDATE users SET password_hash=:p WHERE lower(username)=lower(:u)"
                        ), {"u": ADMIN_SEED_USERNAME, "p": _hash(ADMIN_SEED_PASSWORD)})
                        _store_admin_seed_state(_seed_digest)
                        print(f"[seed] admin '{ADMIN_SEED_USERNAME}' password reset via ADMIN_SEED_FORCE_RESET")
                print(f"[seed] admin '{ADMIN_SEED_USERNAME}' ensured")
except Exception as _e:
    print(f"[seed] admin skipped: {_e}")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _start_background_schedulers()
    try:
        start_custodian_lookup_bootstrap()
    except Exception as exc:
        print(f"[startup] custodian lookup bootstrap skipped: {exc}")

    yield

app = FastAPI(
    title="ediscovery",
    docs_url="/docs" if (os.getenv("DEBUG_ROUTES") == "1" or os.getenv("ENABLE_DOCS") == "1") else None,
    redoc_url=None,
    openapi_url="/openapi.json" if (os.getenv("DEBUG_ROUTES") == "1" or os.getenv("ENABLE_DOCS") == "1") else None,
    lifespan=_lifespan,
)

# File logging with gzip rotation for app/uvicorn logs
try:
    # App/application log: keep compression for larger files
    setup_file_logging()
    # Import logs are small; disable compression
    setup_file_logging(log_name="import.log", compress=False)
except Exception as exc:
    print(f"[logging] file logger setup skipped: {exc}")


def _health_allowed(request: Optional[object]) -> bool:
    """
    Allow health/ready when the configured secret matches.
    If no secret is configured, allow only local callers.
    """
    local_hosts = {"127.0.0.1", "::1", "localhost", "testclient"}
    effective_secret = (os.getenv("HEALTHCHECK_SECRET") or HEALTHCHECK_SECRET or "").strip()

    supplied = None
    try:
        supplied = request.headers.get("X-Health-Secret") if request else None
    except Exception:
        supplied = None

    if effective_secret:
        return supplied is not None and secrets.compare_digest(supplied, effective_secret)

    try:
        scope = getattr(request, "scope", None)
        if scope:
            client_host = (scope.get("client") or [None])[0]
            if client_host in local_hosts:
                return True
    except Exception as exc:
        _debug_suppressed("suppressed exception in main.py:428", exc)
    try:
        client = getattr(request, "client", None)
        host = getattr(client, "host", None)
        return host in local_hosts
    except Exception:
        return False


# -------- health ----------
@app.get("/health", include_in_schema=False)
def health(request: Request):
    if not _health_allowed(request):
        return Response(status_code=403)
    return {"status": "ok"}

@app.get("/api/health", include_in_schema=False)
def api_health(request: Request):
    if not _health_allowed(request):
        return Response(status_code=403)
    return {"status": "ok"}

@app.get("/ready", include_in_schema=False)
def ready(request: Request):
    if not _health_allowed(request):
        return Response(status_code=403)
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    finally:
        db.close()

# -------- CORS ----------
_origins_env = os.getenv("BACKEND_CORS_ORIGINS", "")
_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
if not _origins:
    _origins = ["https://127.0.0.1:10443", "https://localhost:10443", "http://localhost:5173"]
if any(o == "*" for o in _origins):
    if ALLOW_INSECURE_DEV:
        print("[cors] WARNING: wildcard origin allowed due to ALLOW_INSECURE_DEV; do not use '*' in production.")
    else:
        raise RuntimeError("BACKEND_CORS_ORIGINS cannot include '*' when allow_credentials=True. Set explicit origins.")
print(f"[cors] allow_origins={_origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enforce CSRF tokens for state-changing requests when session cookies are present
app.add_middleware(
    CSRFMiddleware,
    cookie_name=os.getenv("CSRF_COOKIE_NAME", "csrf"),
    header_name=os.getenv("CSRF_HEADER_NAME", "X-CSRF-Token"),
    session_cookie=os.getenv("SESSION_COOKIE_NAME", "access_token"),
    skip_paths={"/api/auth/token", "/api/auth/logout", "/api/setup/complete"},
)

# Rate-limit login endpoint + other expensive routes
app.add_middleware(AuthTokenRateLimitMiddleware)
app.add_middleware(ExpensiveEndpointRateLimitMiddleware)
# -------- Suggest Name (never null) ----------
@app.get("/api/cases/suggest_name", include_in_schema=True)
def _suggest_name_proxy(legal_case_name: Optional[str] = Query(None), _user = Depends(current_user)):
    db = SessionLocal()
    try:
        result = None
        try:
            result = _suggest_impl(db, legal_case_name=legal_case_name)
        except Exception:
            result = None

        name = None
        if isinstance(result, dict):
            name = result.get("name")
        else:
            try:
                body = getattr(result, "body", None)
                if body:
                    import json
                    name = json.loads(body).get("name")
            except Exception:
                name = None

        if not name:
            year = datetime.now(timezone.utc).year
            rows = (
                db.query(Case.color, func.count(Case.id))
                  .filter(Case.name.like(f"{year}-%"))
                  .group_by(Case.color)
                  .all()
            )
            counts = {(c or "").strip(): n for c, n in rows}
            COLORS = ["Blue","Green","Red","Yellow","Purple","Orange","Teal","Gray"]
            best = min(COLORS, key=lambda c: counts.get(c, 0))
            name = f"{year}-{best}"
        return {"name": name}
    finally:
        db.close()

# -------- helpers to include routers safely ----------
def _safe_include(getter, **kwargs):
    try:
        app.include_router(getter(), **kwargs)
    except Exception as e:
        logging.getLogger(__name__).exception("include_router failed")
        if not (ALLOW_INSECURE_DEV or ALLOW_PARTIAL_STARTUP):
            raise RuntimeError("Router include failed; refusing partial API startup") from e

# Mount Logs under /api/logs
from .logs import router as logs_router
app.include_router(logs_router)

# Mount Reports under /api/reports/*
from .reports import router as reports_router
app.include_router(reports_router, dependencies=[Depends(current_user)])

from .system_admin import router as system_admin_router
from .system_backups import router as system_backups_router
from .system_branding import router as system_branding_router
from .system_ops import router as system_ops_router
from .email_intake_api import router as email_intake_router
app.include_router(system_admin_router, dependencies=[Depends(current_user)])
app.include_router(system_backups_router, dependencies=[Depends(current_user)])
app.include_router(system_branding_router, dependencies=[Depends(current_user)])
app.include_router(system_ops_router, dependencies=[Depends(current_user)])
app.include_router(email_intake_router, dependencies=[Depends(current_user)])

from .case_requests import router as case_requests_router
from .case_request_files import router as case_request_files_router
from .case_request_lookup import router as case_request_lookup_router
from .case_request_custodian_uploads import router as case_request_custodian_uploads_router
from .case_request_read import router as case_request_read_router
from .case_request_review import router as case_request_review_router
from .case_request_create import router as case_request_create_router
from .case_request_approval import router as case_request_approval_router
app.include_router(case_requests_router, dependencies=[Depends(current_user)])
app.include_router(case_request_files_router, dependencies=[Depends(current_user)])
app.include_router(case_request_lookup_router, dependencies=[Depends(current_user)])
app.include_router(case_request_custodian_uploads_router, dependencies=[Depends(current_user)])
app.include_router(case_request_read_router, dependencies=[Depends(current_user)])
app.include_router(case_request_review_router, dependencies=[Depends(current_user)])
app.include_router(case_request_create_router, dependencies=[Depends(current_user)])
app.include_router(case_request_approval_router, dependencies=[Depends(current_user)])
app.include_router(ai_assistant_router, dependencies=[Depends(current_user)])

from .setup import router as setup_router
app.include_router(setup_router)

from .ntp_templates import router as ntp_templates_router
from .ntp_history import router as ntp_history_router
from .ntp import router as ntp_router, acknowledge_ntp, confirm_ntp_acknowledgement, start_ntp_reminder_scheduler
from .case_closure import start_case_closure_scheduler
from .consent_notifications import start_weekly_pending_consent_scheduler
from .search_delivery_reminders import start_search_delivery_reminder_scheduler
from .purview_exports import start_purview_export_scheduler
from .account_reviews import start_account_review_scheduler
from .email_intake_scheduler import start_email_intake_scheduler
from .slack_oauth import router as slack_oauth_router
app.include_router(ntp_templates_router)
app.include_router(ntp_history_router)
app.include_router(ntp_router)
app.include_router(slack_oauth_router)

# Other routers (these usually already prefix with /api inside each module)
def _auth_sso_router():
    from .auth_sso import router as r
    return r
_safe_include(_auth_sso_router)

def _auth_registration_router():
    from .auth_registration import router as r
    return r
_safe_include(_auth_registration_router)

def _auth_router():
    from .auth import router as r
    return r
_safe_include(_auth_router)

def _users_groups_router():
    from .users_groups import router as r
    return r
_safe_include(_users_groups_router, dependencies=[Depends(current_user)])

def _users_router():
    from .users import router as r
    return r
_safe_include(_users_router, dependencies=[Depends(current_user)])

def _case_ticketing_emails_router():
    from .case_ticketing_emails import router as r
    return r
_safe_include(_case_ticketing_emails_router, dependencies=[Depends(current_user)])

def _case_ticketing_router():
    from .case_ticketing import router as r
    return r
_safe_include(_case_ticketing_router, dependencies=[Depends(current_user)])

def _case_status_summary_router():
    from .case_status_summary import router as r
    return r
_safe_include(_case_status_summary_router, dependencies=[Depends(current_user)])

def _case_consents_router():
    from .case_consents import router as r
    return r
_safe_include(_case_consents_router, dependencies=[Depends(current_user)])

def _case_naming_router():
    from .case_naming import router as r
    return r
_safe_include(_case_naming_router, dependencies=[Depends(current_user)])

def _case_requestors_router():
    from .case_requestors import router as r
    return r
_safe_include(_case_requestors_router, dependencies=[Depends(current_user)])
def _case_custodians_router():
    from .case_custodians import router as r
    return r
_safe_include(_case_custodians_router, dependencies=[Depends(current_user)])
def _case_holds_router():
    from .case_holds import router as r
    return r
_safe_include(_case_holds_router, dependencies=[Depends(current_user)])

def _case_purview_router():
    from .case_purview import router as r
    return r
_safe_include(_case_purview_router, dependencies=[Depends(current_user)])

def _cases_router():
    from .cases import router as r
    return r
_safe_include(_cases_router, dependencies=[Depends(current_user)])

def _search_ai_router():
    from .search_ai import router as r
    return r
_safe_include(_search_ai_router, dependencies=[Depends(current_user)])

def _searches_router():
    from .searches import router as r
    return r
_safe_include(_searches_router, dependencies=[Depends(current_user)])

def _purview_exports_router():
    from .purview_exports import router as r
    return r
_safe_include(_purview_exports_router, dependencies=[Depends(current_user)])

def _docusign_webhook_router():
    from .docusign_webhook import router as r
    return r
_safe_include(_docusign_webhook_router)

def _note_attachments_router():
    from .note_attachments import router as r
    return r
_safe_include(_note_attachments_router, dependencies=[Depends(current_user)])

def _notes_router():
    from .notes import router as r
    return r
_safe_include(_notes_router, dependencies=[Depends(current_user)])

def _custodians_router():
    from .custodians_summary import router as r
    return r
_safe_include(_custodians_router, dependencies=[Depends(current_user)])

def _dashboards_router():
    from .dashboards import router as r
    return r
_safe_include(_dashboards_router, dependencies=[Depends(current_user)])

@app.get("/ntp/ack/{token}", include_in_schema=False)
def ntp_acknowledge(token: str):
    return acknowledge_ntp(token, action_path=f"/ntp/ack/{token}")

@app.get("/api/ntp/ack/{token}", include_in_schema=False)
def api_ntp_acknowledge(token: str):
    return acknowledge_ntp(token, action_path=f"/api/ntp/ack/{token}")

@app.post("/ntp/ack/{token}", include_in_schema=False)
def ntp_acknowledge_confirm(token: str):
    return confirm_ntp_acknowledgement(token)

@app.post("/api/ntp/ack/{token}", include_in_schema=False)
def api_ntp_acknowledge_confirm(token: str):
    return confirm_ntp_acknowledgement(token)

# Simple JSON route list to verify what's mounted (no /api on purpose)
if os.getenv("DEBUG_ROUTES") == "1":
    @app.get("/debug/routes", include_in_schema=False)
    def debug_routes():
        from fastapi.routing import APIRoute
        return {"routes": [r.path for r in app.router.routes if isinstance(r, APIRoute)]}


# === Appends by Code Copilot (instrumentation & security middleware) ===
try:
    from prometheus_fastapi_instrumentator import Instrumentator
except Exception:
    Instrumentator = None
from .middleware import RequestIDMiddleware

# Avoid duplicate registration if reloaded
try:
    _cc_middlewares_added
except NameError:
    app.add_middleware(RequestIDMiddleware)
    _metrics_enabled = bool((os.getenv("ENABLE_METRICS") or "").strip())
    _instrumentator = None
    if _metrics_enabled and Instrumentator is not None:
        _instrumentator = Instrumentator()
        _instrumentator.instrument(app)
    elif _metrics_enabled and Instrumentator is None:
        print("[metrics] prometheus_fastapi_instrumentator is unavailable; metrics middleware disabled")
    _cc_middlewares_added = True

# Health & readiness if missing
from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from .database import get_db

if not any([r.path == "/healthz" for r in app.router.routes if hasattr(r, "path")]):
    @app.get("/healthz")
    def healthz(request: Request):
        if not _health_allowed(request):
            return Response(status_code=403)
        return {"status": "ok"}

if not any([r.path == "/readyz" for r in app.router.routes if hasattr(r, "path")]):
    @app.get("/readyz")
    def readyz(request: Request, db: Session = Depends(get_db)):
        if not _health_allowed(request):
            return Response(status_code=403)
        db.execute(text("SELECT 1"))
        return {"db": "ok"}
# === End appends ===

# === Appends by Code Copilot (do not edit) ===
try:
    from .middleware import RequestSizeLimitMiddleware
    app.add_middleware(RequestSizeLimitMiddleware)
except Exception as exc:
    _debug_suppressed("suppressed exception in main.py:675", exc)

try:
    from .ratelimit import RateLimitMiddleware, load_rules_from_env, rate_limit_stats
    import os
    _default_rate_rules = [
        (r"^/api/auth/token$", "POST", 10, 60),
        (r"^/api/cases", "POST", 60, 60),
        (r"^/api/cases", "DELETE", 30, 60),
        (r"^/api/case_requests/custodian_lookup$", "POST", 20, 60),
        (r"^/api/case_requests/parse_custodian_file$", "POST", 10, 60),
        (r"^/api/system/backups/restore$", "POST", 3, 3600),
    ]
    if RATE_LIMITS_ENABLED:
        rules = load_rules_from_env(defaults=_default_rate_rules)
        if rules:
            _rl_redis_url = os.getenv("RATE_LIMIT_REDIS_URL") or os.getenv("REDIS_URL")
            app.add_middleware(RateLimitMiddleware, rules=rules, redis_url=_rl_redis_url)

            @app.get("/api/system/rate_limits", dependencies=[Depends(require_admin)], include_in_schema=False)
            def rate_limits_status():
                return {"rules": rate_limit_stats(rules, _rl_redis_url)}
        else:
            print("[rate-limit] no rules loaded; middleware not added")
except Exception as exc:
    print(f"[rate-limit] middleware not installed: {exc}")

from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def _unhandled(request, exc):
    rid = getattr(getattr(request, "state", None), "request_id", None)
    try:
        path = str(request.url.path) if hasattr(request, "url") else None
    except Exception:
        path = None
    logger.exception(
        "Unhandled exception",
        extra={"request_id": rid, "path": path},
    )
    return JSONResponse(
        {"detail": "internal_error", "request_id": rid},
        status_code=500,
    )
# === End Appends ===


def _start_background_schedulers() -> None:
    if not ENABLE_SCHEDULERS:
        print("[startup] background schedulers disabled via ENABLE_SCHEDULERS")
        return
    if not _acquire_scheduler_lock():
        if REQUIRE_SCHEDULER_LOCK:
            print("[startup] scheduler lock unavailable; background jobs will not start")
        else:
            print("[startup] scheduler lock held by another process; skipping background jobs")
        return
    start_ntp_reminder_scheduler()
    start_backup_scheduler()
    start_log_ship_scheduler()
    start_db_maintenance_scheduler()
    notify_missing_backup_key()
    start_case_request_cleanup()
    start_case_closure_scheduler()
    start_weekly_pending_consent_scheduler()
    start_search_delivery_reminder_scheduler()
    start_purview_export_scheduler()
    start_account_review_scheduler()
    start_email_intake_scheduler()
    try:
        sync_case_request_attachment_bytes()
    except Exception as exc:
        print(f"[bootstrap] case request attachment sync skipped: {exc}")
    try:
        check_upload_scanner_ready()
    except Exception as exc:
        print(f"[startup] upload scanner readiness check failed: {exc}")



if "_instrumentator" in globals() and _instrumentator and _PROMETHEUS_CLIENT_AVAILABLE and generate_latest is not None:
    metrics_router = APIRouter()

    @metrics_router.get("/metrics", include_in_schema=False)
    def metrics_endpoint(_: object = Depends(require_admin)):
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(metrics_router)
