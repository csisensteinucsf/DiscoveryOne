from __future__ import annotations

import fnmatch
import logging
import os
import socket
import tarfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

import httpx

from .audit import log_event
from .database import SessionLocal
from .integration_settings import decrypt_secret
from .runtime_paths import runtime_dir
from .safe_log import debug_suppressed as _debug_suppressed
from .system_settings import load_stored_system_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LogShippingSettings:
    enabled: bool
    interval_hours: float
    run_on_startup: bool
    target: str
    graph_base: str
    scope: str
    timeout_seconds: float
    retry_count: int
    tenant_id: str
    client_id: str
    client_secret: str
    sharepoint_site_id: str
    sharepoint_drive_id: str
    sharepoint_drive_name: str
    sharepoint_folder: str
    max_file_mb: float
    max_archive_mb: float
    max_files: int
    work_dir: Path
    include_globs: str
    exclude_globs: str
    delete_local_archive: bool
    startup_delay_seconds: float


_scheduler_started = False
_token_cache: dict[str, Any] = {
    "token": None,
    "expires_at": 0.0,
    "settings_key": None,
}


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_value(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            return value
    return None


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def load_log_shipping_settings() -> LogShippingSettings:
    """Load the current app-managed configuration with per-field legacy env fallback."""
    try:
        stored = load_stored_system_settings()
    except Exception:
        stored = {}

    enabled_values = stored.get("enabled_integrations")
    if not isinstance(enabled_values, dict):
        enabled_values = {}
    configs = stored.get("integration_configs")
    if not isinstance(configs, dict):
        configs = {}
    configured = configs.get("log_shipping")
    if not isinstance(configured, dict):
        configured = {}
    settings_ready = bool(stored.get("initial_setup_completed"))

    def value(key: str, env_names: tuple[str, ...], default: Any) -> Any:
        if key in configured:
            return configured.get(key)
        if settings_ready:
            return default
        env_value = _env_value(*env_names)
        return default if env_value is None else env_value

    if "log_shipping" in enabled_values:
        enabled = _truthy(enabled_values.get("log_shipping"))
    elif settings_ready:
        enabled = False
    else:
        enabled = _truthy(_env_value("LOG_SHIP_ENABLED"))

    interval_hours = _bounded_float(
        value("interval_hours", ("LOG_SHIP_INTERVAL_HOURS",), 24),
        24,
        1,
        720,
    )
    timeout_seconds = _bounded_float(
        value("timeout_seconds", ("LOG_SHIP_TIMEOUT_SECONDS",), 120),
        120,
        5,
        300,
    )
    retry_count = _bounded_int(
        value("retry_count", ("LOG_SHIP_RETRY_COUNT",), 3),
        3,
        0,
        10,
    )
    max_file_mb = _bounded_float(
        value("max_file_mb", ("LOG_SHIP_MAX_FILE_MB",), 250),
        250,
        1,
        250,
    )
    max_archive_mb = _bounded_float(
        value("max_archive_mb", ("LOG_SHIP_MAX_ARCHIVE_MB",), 250),
        250,
        1,
        250,
    )
    max_files = _bounded_int(
        value("max_files", ("LOG_SHIP_MAX_FILES",), 5000),
        5000,
        1,
        5000,
    )

    graph_base = str(
        value(
            "graph_base",
            ("LOG_SHIP_GRAPH_BASE",),
            "https://graph.microsoft.com/v1.0",
        )
        or "https://graph.microsoft.com/v1.0"
    ).strip().rstrip("/")
    scope = str(
        value(
            "scope",
            ("LOG_SHIP_SCOPE",),
            "https://graph.microsoft.com/.default",
        )
        or "https://graph.microsoft.com/.default"
    ).strip()

    return LogShippingSettings(
        enabled=enabled,
        interval_hours=interval_hours,
        run_on_startup=_truthy(
            value("run_on_startup", ("LOG_SHIP_RUN_ON_STARTUP",), True),
            default=True,
        ),
        target="sharepoint",
        graph_base=graph_base,
        scope=scope,
        timeout_seconds=timeout_seconds,
        retry_count=retry_count,
        tenant_id=str(
            value(
                "tenant_id",
                ("LOG_SHIP_TENANT_ID", "PURVIEW_TENANT_ID", "O365_TENANT_ID"),
                "",
            )
            or ""
        ).strip(),
        client_id=str(
            value(
                "client_id",
                ("LOG_SHIP_CLIENT_ID", "PURVIEW_CLIENT_ID", "O365_CLIENT_ID"),
                "",
            )
            or ""
        ).strip(),
        client_secret=decrypt_secret(
            value(
                "client_secret",
                (
                    "LOG_SHIP_CLIENT_SECRET",
                    "PURVIEW_CLIENT_SECRET",
                    "O365_CLIENT_SECRET",
                ),
                "",
            )
        ),
        sharepoint_site_id=str(
            value(
                "sharepoint_site_id",
                ("LOG_SHIP_SHAREPOINT_SITE_ID",),
                "",
            )
            or ""
        ).strip(),
        sharepoint_drive_id=str(
            value(
                "sharepoint_drive_id",
                ("LOG_SHIP_SHAREPOINT_DRIVE_ID",),
                "",
            )
            or ""
        ).strip(),
        sharepoint_drive_name=str(
            value(
                "sharepoint_drive_name",
                ("LOG_SHIP_SHAREPOINT_DRIVE_NAME",),
                "",
            )
            or ""
        ).strip(),
        sharepoint_folder=str(
            value(
                "sharepoint_folder",
                ("LOG_SHIP_SHAREPOINT_FOLDER",),
                "DiscoveryOneLogs",
            )
            or ""
        ).strip().strip("/"),
        max_file_mb=max_file_mb,
        max_archive_mb=max_archive_mb,
        max_files=max_files,
        work_dir=Path(
            os.getenv("LOG_SHIP_WORK_DIR", str(runtime_dir() / "log_ship"))
        ),
        include_globs=os.getenv(
            "LOG_SHIP_INCLUDE_GLOBS",
            "*.log,*.log.*,*.gz",
        ),
        exclude_globs=os.getenv("LOG_SHIP_EXCLUDE_GLOBS", ""),
        delete_local_archive=_truthy(
            os.getenv("LOG_SHIP_DELETE_LOCAL_ARCHIVE"),
            default=True,
        ),
        startup_delay_seconds=_bounded_float(
            os.getenv("LOG_SHIP_STARTUP_DELAY_SECONDS", "120"),
            120,
            0,
            3600,
        ),
    )


def _parse_patterns(raw: str) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part and part.strip()]


def _matches_any(path: Path, patterns: list[str]) -> bool:
    if not patterns:
        return False
    name = path.name.lower()
    rel = path.as_posix().lower()
    for pattern in patterns:
        normalized = pattern.lower()
        if fnmatch.fnmatch(name, normalized) or fnmatch.fnmatch(rel, normalized):
            return True
    return False


def _log_dirs() -> list[tuple[str, Path]]:
    candidates: list[tuple[str, str]] = [
        ("logs", os.getenv("LOG_DIR") or "/app/logs"),
        ("audit", os.getenv("AUDIT_LOG_DIR") or (os.getenv("LOG_DIR") or "/app/logs")),
        (
            "backup",
            str(Path(os.getenv("BACKUP_LOG_FILE") or "/app/logs/backup.log").parent),
        ),
    ]
    seen: set[str] = set()
    resolved: list[tuple[str, Path]] = []
    for label, raw in candidates:
        if not raw:
            continue
        path = Path(raw).expanduser()
        if path.is_file():
            path = path.parent
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in seen:
            continue
        if not path.exists() or not path.is_dir():
            continue
        seen.add(key)
        resolved.append((label, path))
    return resolved


def _collect_log_files(
    settings: LogShippingSettings,
) -> tuple[list[tuple[str, Path]], list[dict[str, Any]]]:
    include = _parse_patterns(settings.include_globs)
    exclude = _parse_patterns(settings.exclude_globs)
    max_file_bytes = int(settings.max_file_mb * 1024 * 1024)
    files: list[tuple[str, Path]] = []
    skipped: list[dict[str, Any]] = []

    for label, base in _log_dirs():
        try:
            all_files = sorted([path for path in base.rglob("*") if path.is_file()])
        except OSError:
            continue
        for path in all_files:
            if include and not _matches_any(path, include):
                continue
            if exclude and _matches_any(path, exclude):
                continue
            try:
                size = int(path.stat().st_size)
            except (OSError, ValueError, TypeError):
                continue
            if size > max_file_bytes:
                skipped.append(
                    {"path": str(path), "reason": "file_too_large", "size": size}
                )
                continue
            files.append((label, path))
            if len(files) >= settings.max_files:
                skipped.append(
                    {
                        "path": str(path),
                        "reason": "max_files_reached",
                        "max_files": settings.max_files,
                    }
                )
                return files, skipped
    return files, skipped


def _build_archive(
    settings: LogShippingSettings,
) -> tuple[Optional[Path], dict[str, Any]]:
    files, skipped = _collect_log_files(settings)
    details: dict[str, Any] = {
        "selected_files": len(files),
        "skipped": skipped[:200],
    }
    if not files:
        details["status"] = "no_files"
        return None, details

    settings.work_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    host = (socket.gethostname() or "host").split(".")[0]
    archive_path = settings.work_dir / f"discoveryone-logs-{host}-{stamp}.tar.gz"

    dirs_by_label = {label: base for label, base in _log_dirs()}
    try:
        with tarfile.open(archive_path, mode="w:gz") as archive:
            for label, path in files:
                base = dirs_by_label.get(label)
                if not base:
                    continue
                try:
                    rel = path.relative_to(base)
                except Exception:
                    rel = Path(path.name)
                archive.add(
                    path,
                    arcname=f"{label}/{rel.as_posix()}",
                    recursive=False,
                )
    except Exception as exc:
        details["status"] = "archive_failed"
        details["error"] = str(exc)
        try:
            if archive_path.exists():
                archive_path.unlink()
        except Exception as cleanup_exc:
            _debug_suppressed(
                "suppressed exception in log_shipping.py:archive_cleanup",
                cleanup_exc,
            )
        return None, details

    try:
        archive_size = int(archive_path.stat().st_size)
    except Exception:
        archive_size = 0
    details["archive_path"] = str(archive_path)
    details["archive_size"] = archive_size

    max_archive_bytes = int(settings.max_archive_mb * 1024 * 1024)
    if archive_size > max_archive_bytes:
        details["status"] = "archive_too_large"
        details["max_archive_bytes"] = max_archive_bytes
        try:
            archive_path.unlink()
        except Exception as cleanup_exc:
            _debug_suppressed(
                "suppressed exception in log_shipping.py:oversized_cleanup",
                cleanup_exc,
            )
        return None, details

    details["status"] = "archive_ready"
    return archive_path, details


def _http_request(
    settings: LogShippingSettings,
    method: str,
    url: str,
    *,
    headers: Optional[dict[str, str]] = None,
    data: Any = None,
    json: Any = None,
) -> httpx.Response:
    last_exc: Optional[Exception] = None
    for attempt in range(settings.retry_count + 1):
        try:
            response = httpx.request(
                method,
                url,
                headers=headers,
                data=data,
                json=json,
                timeout=settings.timeout_seconds,
            )
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            last_exc = exc
            if attempt >= settings.retry_count:
                raise
            time.sleep(min(10.0, 0.5 * (2 ** attempt)))
            continue
        if (
            response.status_code in {429, 500, 502, 503, 504}
            and attempt < settings.retry_count
        ):
            time.sleep(min(15.0, 0.75 * (2 ** attempt)))
            continue
        return response
    if last_exc:
        raise last_exc
    raise RuntimeError("log ship request failed")


def _graph_token(settings: LogShippingSettings) -> str:
    now = time.time()
    settings_key = (
        settings.tenant_id,
        settings.client_id,
        settings.client_secret,
        settings.scope,
    )
    cached = _token_cache.get("token")
    if (
        cached
        and _token_cache.get("settings_key") == settings_key
        and float(_token_cache.get("expires_at", 0.0) or 0.0) > now + 30
    ):
        return str(cached)
    if not settings.tenant_id or not settings.client_id or not settings.client_secret:
        raise RuntimeError("Log shipping tenant/client credentials are not configured")

    token_url = (
        f"https://login.microsoftonline.com/{settings.tenant_id}/oauth2/v2.0/token"
    )
    response = _http_request(
        settings,
        "POST",
        token_url,
        data={
            "client_id": settings.client_id,
            "client_secret": settings.client_secret,
            "scope": settings.scope,
            "grant_type": "client_credentials",
        },
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"token request failed ({response.status_code}): {response.text[:300]}"
        )
    payload = response.json()
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("token response missing access_token")
    expires_in = int(payload.get("expires_in") or 3600)
    _token_cache["token"] = token
    _token_cache["expires_at"] = now + max(30, expires_in - 30)
    _token_cache["settings_key"] = settings_key
    return token


def _graph_json(
    settings: LogShippingSettings,
    method: str,
    url: str,
    token: str,
    *,
    json_payload: Any = None,
    allow_statuses: Optional[set[int]] = None,
) -> tuple[int, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    response = _http_request(
        settings,
        method,
        url,
        headers=headers,
        json=json_payload,
    )
    if allow_statuses and response.status_code in allow_statuses:
        try:
            return response.status_code, response.json()
        except Exception:
            return response.status_code, response.text
    if response.status_code >= 400:
        raise RuntimeError(
            f"Graph request failed ({response.status_code}): {response.text[:400]}"
        )
    if response.status_code == 204:
        return response.status_code, None
    try:
        return response.status_code, response.json()
    except Exception:
        return response.status_code, response.text


def _resolve_drive_id(
    settings: LogShippingSettings,
    token: str,
    site_id: str,
) -> str:
    if settings.sharepoint_drive_id:
        return settings.sharepoint_drive_id
    if not settings.sharepoint_drive_name:
        raise RuntimeError("SharePoint drive ID or drive name is required")
    list_url = f"{settings.graph_base}/sites/{site_id}/drives?=200"
    _, payload = _graph_json(settings, "GET", list_url, token)
    items = payload.get("value") if isinstance(payload, dict) else []
    target = settings.sharepoint_drive_name.strip().lower()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip().lower()
        drive_id = (item.get("id") or "").strip()
        if name == target and drive_id:
            return drive_id
    raise RuntimeError(
        f"SharePoint drive not found by name: {settings.sharepoint_drive_name}"
    )


def _ensure_sharepoint_folder(
    settings: LogShippingSettings,
    token: str,
    site_id: str,
    drive_id: str,
    folder_path: str,
) -> None:
    folder = (folder_path or "").strip().strip("/")
    if not folder:
        return

    parent_id = None
    built = ""
    for segment in [part for part in folder.split("/") if part]:
        built = f"{built}/{segment}" if built else segment
        get_url = (
            f"{settings.graph_base}/sites/{site_id}/drives/{drive_id}"
            f"/root:/{quote(built, safe='/')}"
        )
        status, payload = _graph_json(
            settings,
            "GET",
            get_url,
            token,
            allow_statuses={404},
        )
        if status == 404:
            if parent_id:
                create_url = (
                    f"{settings.graph_base}/sites/{site_id}/drives/{drive_id}"
                    f"/items/{parent_id}/children"
                )
            else:
                create_url = (
                    f"{settings.graph_base}/sites/{site_id}/drives/{drive_id}"
                    "/root/children"
                )
            _, payload = _graph_json(
                settings,
                "POST",
                create_url,
                token,
                json_payload={
                    "name": segment,
                    "folder": {},
                    "@microsoft.graph.conflictBehavior": "replace",
                },
            )
        if isinstance(payload, dict):
            parent_id = payload.get("id")


def _upload_archive_to_sharepoint(
    settings: LogShippingSettings,
    archive_path: Path,
) -> dict[str, Any]:
    if settings.target != "sharepoint":
        raise RuntimeError(f"unsupported LOG_SHIP_TARGET={settings.target}")
    if not settings.sharepoint_site_id:
        raise RuntimeError("SharePoint site ID is required")

    token = _graph_token(settings)
    drive_id = _resolve_drive_id(
        settings,
        token,
        settings.sharepoint_site_id,
    )
    _ensure_sharepoint_folder(
        settings,
        token,
        settings.sharepoint_site_id,
        drive_id,
        settings.sharepoint_folder,
    )

    remote_path = archive_path.name
    if settings.sharepoint_folder:
        remote_path = f"{settings.sharepoint_folder}/{remote_path}"

    url = (
        f"{settings.graph_base}/sites/{settings.sharepoint_site_id}"
        f"/drives/{drive_id}/root:/{quote(remote_path, safe='/')}:/content"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/gzip",
    }
    with archive_path.open("rb") as archive_file:
        response = _http_request(
            settings,
            "PUT",
            url,
            headers=headers,
            data=archive_file,
        )
    if response.status_code not in {200, 201}:
        raise RuntimeError(
            f"upload failed ({response.status_code}): {response.text[:400]}"
        )

    payload = response.json() if response.text else {}
    web_url = payload.get("webUrl") if isinstance(payload, dict) else None
    return {
        "remote_path": remote_path,
        "status_code": response.status_code,
        "web_url": web_url,
    }


def _audit(action: str, details: dict[str, Any]) -> None:
    db = SessionLocal()
    try:
        log_event(
            db,
            action=action,
            actor_id=None,
            target_type="system",
            target_id=None,
            details=details,
            request=None,
        )
    except Exception as exc:
        _debug_suppressed("suppressed exception in log_shipping.py:audit", exc)
    finally:
        db.close()


def _run_once(settings: Optional[LogShippingSettings] = None) -> None:
    current = settings or load_log_shipping_settings()
    if not current.enabled:
        logger.info("log ship run skipped because integration is disabled")
        return

    archive_path, details = _build_archive(current)
    details["target"] = current.target
    details["interval_hours"] = current.interval_hours

    if not archive_path:
        logger.info(
            "log ship skipped status=%s selected_files=%s",
            details.get("status"),
            details.get("selected_files"),
        )
        _audit("log_ship_run", details)
        return

    try:
        upload = _upload_archive_to_sharepoint(current, archive_path)
        details.update(
            {
                "status": "uploaded",
                "upload": upload,
            }
        )
        logger.info(
            "log ship uploaded archive=%s bytes=%s remote=%s",
            archive_path,
            details.get("archive_size"),
            upload.get("remote_path"),
        )
        _audit("log_ship_run", details)
    except Exception as exc:
        details.update(
            {
                "status": "upload_failed",
                "error": str(exc),
            }
        )
        logger.warning("log ship failed archive=%s error=%s", archive_path, exc)
        _audit("log_ship_failed", details)
    finally:
        if current.delete_local_archive:
            try:
                archive_path.unlink(missing_ok=True)
            except Exception as cleanup_exc:
                _debug_suppressed(
                    "suppressed exception in log_shipping.py:run_cleanup",
                    cleanup_exc,
                )


def start_log_ship_scheduler() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True

    def _worker() -> None:
        initial = load_log_shipping_settings()
        if initial.startup_delay_seconds > 0:
            time.sleep(initial.startup_delay_seconds)

        next_run_at: Optional[float] = None
        schedule_signature: Optional[tuple[float, bool]] = None
        while True:
            current = load_log_shipping_settings()
            now = time.time()
            if not current.enabled:
                next_run_at = None
                schedule_signature = None
                time.sleep(30.0)
                continue

            current_signature = (
                current.interval_hours,
                current.run_on_startup,
            )
            if next_run_at is None:
                next_run_at = (
                    now
                    if current.run_on_startup
                    else now + (current.interval_hours * 3600)
                )
            elif schedule_signature != current_signature:
                next_run_at = now + (current.interval_hours * 3600)
            schedule_signature = current_signature

            if now < next_run_at:
                time.sleep(min(30.0, next_run_at - now))
                continue

            try:
                _run_once(current)
            except Exception as exc:
                logger.exception("log ship scheduler iteration failed: %s", exc)
            finally:
                refreshed = load_log_shipping_settings()
                next_run_at = time.time() + (refreshed.interval_hours * 3600)
                schedule_signature = (
                    refreshed.interval_hours,
                    refreshed.run_on_startup,
                )

    thread = threading.Thread(
        target=_worker,
        daemon=True,
        name="log-ship-scheduler",
    )
    thread.start()
