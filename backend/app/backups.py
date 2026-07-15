from __future__ import annotations

import base64
import gzip
import logging
from logging.handlers import RotatingFileHandler
import os
import shutil
import subprocess  # nosec B404
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import or_, text

from .app_branding import branded_subject
from .database import DATABASE_URL, engine, SessionLocal
from . import models
from .emailer import mail_provider_ready, send_email
from .notifications import _send_teams_notification
from .runtime_paths import runtime_file
from .safe_log import debug_suppressed as _debug_suppressed
from .system_settings import load_system_settings

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/app/backups"))
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_LOG_FILE = Path(os.getenv("BACKUP_LOG_FILE", "/app/logs/backup.log"))
try:
    BACKUP_LOG_MAX_MB = float(os.getenv("BACKUP_LOG_MAX_MB", os.getenv("LOG_MAX_MB", os.getenv("AUDIT_LOG_MAX_MB", "0.1"))))
except Exception:
    BACKUP_LOG_MAX_MB = 0.1
BACKUP_LOG_BACKUP_COUNT = int(os.getenv("BACKUP_LOG_BACKUP_COUNT", os.getenv("LOG_BACKUP_COUNT", os.getenv("AUDIT_LOG_BACKUP_COUNT", "20"))))
ALLOW_PLAINTEXT_BACKUPS = (os.getenv("ALLOW_PLAINTEXT_BACKUPS") or "").strip().lower() in {"1", "true", "yes", "on"}
BACKUP_SCHEDULER_LOCK_FILE = os.getenv("BACKUP_SCHEDULER_LOCK_FILE", runtime_file("ediscovery_backup_scheduler.lock"))
BACKUP_REQUIRE_LOCK = (os.getenv("BACKUP_REQUIRE_LOCK") or "1").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_tool(env_name: str, binary: str) -> str:
    override = os.getenv(env_name)
    if override:
        override_path = Path(override)
        if override_path.exists():
            return str(override_path)
        found = shutil.which(override)
        if found:
            return found
    found = shutil.which(binary)
    return found or binary


PG_DUMP_PATH = _resolve_tool("PG_DUMP_PATH", "pg_dump")
PG_RESTORE_PATH = _resolve_tool("PG_RESTORE_PATH", "pg_restore")
PSQL_PATH = _resolve_tool("PSQL_PATH", "psql")
RESTORE_TIMEOUT_SECONDS = int(os.getenv("RESTORE_TIMEOUT_SECONDS", "600"))
SESSION_KILL_INTERVAL = float(os.getenv("RESTORE_SESSION_KILL_INTERVAL", "1.0"))
RESTORE_TERMINATE_CONNECTIONS = (os.getenv("RESTORE_TERMINATE_CONNECTIONS") or "").strip().lower() in {"1", "true", "yes", "on"}
_require_encrypted_default = "0" if ALLOW_PLAINTEXT_BACKUPS else "1"
RESTORE_REQUIRE_ENCRYPTED = (os.getenv("RESTORE_REQUIRE_ENCRYPTED", _require_encrypted_default) or "").strip().lower() in {"1", "true", "yes", "on"}
RESTORE_COOLDOWN_SECONDS = int(os.getenv("RESTORE_COOLDOWN_SECONDS", "300"))
_CHUNK_SIZE = 1024 * 1024
_MAGIC = b"BKP1"
_VERSION = b"\x01"
_IV_SIZE = 16
_MAC_SIZE = 32
_KEY_CACHE: Optional[Tuple[bytes, bytes]] = None

_scheduler_started = False
_restore_lock = threading.Lock()
_last_restore_epoch: Optional[float] = None
_scheduler_lock_fd: Optional[int] = None
_missing_key_alerted = False


def _backup_settings() -> dict:
    try:
        settings = load_system_settings().get("backups") or {}
    except Exception:
        settings = {}
    return settings if isinstance(settings, dict) else {}


def _bounded_float(value, default: float, *, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def backup_automatic_enabled() -> bool:
    return bool(_backup_settings().get("automatic_enabled", True))


def backup_interval_hours() -> float:
    return _bounded_float(_backup_settings().get("interval_hours"), 6.0, minimum=1.0, maximum=168.0)


def backup_retention_hours() -> float:
    return _bounded_float(_backup_settings().get("retention_hours"), 48.0, minimum=1.0, maximum=8760.0)


def _last_scheduled_backup_epoch(mgr: "DatabaseBackupManager") -> Optional[float]:
    """Return the unix timestamp of the most recent scheduled backup if available."""
    try:
        for record in mgr.list_backups():
            label = mgr.extract_label(record.name)
            if label == "scheduled":
                try:
                    return datetime.fromisoformat(record.created_at).timestamp()
                except ValueError:
                    continue
    except Exception as exc:
        _append_log(f"Unable to inspect existing backups: {exc}")
    return None


def _acquire_backup_scheduler_lock() -> bool:
    """Best-effort cross-process guard so only one backup scheduler runs."""
    global _scheduler_lock_fd
    lock_path = (BACKUP_SCHEDULER_LOCK_FILE or "").strip()
    if not lock_path:
        return not BACKUP_REQUIRE_LOCK
    if fcntl is None:
        if BACKUP_REQUIRE_LOCK:
            return False
        return True
    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return True  # fall back to per-process guard
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _scheduler_lock_fd = fd
        return True
    except (BlockingIOError, OSError):
        try:
            os.close(fd)
        except OSError:
            pass
        return False


def _normalize_url(url: str) -> str:
    # pg_dump expects postgresql:// not postgresql+psycopg2://
    for suffix in ("+psycopg2", "+psycopg"):
        if suffix in url:
            return url.replace(suffix, "", 1)
    return url


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_BACKUP_LOGGER: Optional[logging.Logger] = None




def _rollover_if_oversized(handler: RotatingFileHandler) -> None:
    """Rotate immediately when backup.log already exceeds maxBytes."""
    try:
        max_bytes = int(getattr(handler, "maxBytes", 0) or 0)
        base_name = getattr(handler, "baseFilename", "") or ""
        if max_bytes <= 0 or not base_name:
            return
        path = Path(base_name)
        if not path.exists() or path.stat().st_size < max_bytes:
            return
        handler.doRollover()
    except Exception as exc:
        _debug_suppressed("suppressed exception in backups.py:153", exc)

def _backup_logger() -> logging.Logger:
    """Return a gzip-rotating logger for backup.log (idempotent)."""
    global _BACKUP_LOGGER
    if _BACKUP_LOGGER:
        return _BACKUP_LOGGER

    lg = logging.getLogger("backup.file")
    if not any(isinstance(h, RotatingFileHandler) for h in lg.handlers):
        BACKUP_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            BACKUP_LOG_FILE,
            maxBytes=max(1, int(BACKUP_LOG_MAX_MB * 1024 * 1024)),
            backupCount=BACKUP_LOG_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )

        def _namer(path: str) -> str:
            return path + ".gz"

        def _rotator(src: str, dest: str) -> None:
            try:
                with open(src, "rb") as sf, gzip.open(dest, "wb") as df:
                    shutil.copyfileobj(sf, df)
                _secure_path(Path(dest), 0o600)
            finally:
                try:
                    os.remove(src)
                except FileNotFoundError:
                    pass

        handler.namer = _namer
        handler.rotator = _rotator
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S%z",
            )
        )
        lg.addHandler(handler)
        _rollover_if_oversized(handler)
    for h in list(lg.handlers):
        if isinstance(h, RotatingFileHandler):
            _rollover_if_oversized(h)
    lg.setLevel(logging.INFO)
    lg.propagate = False
    _BACKUP_LOGGER = lg
    return lg


def _append_log(message: str) -> None:
    entry = f"[{_now_iso()}] {message}"
    try:
        _backup_logger().info(entry)
    except Exception as exc:
        # Fallback so operators still see the failure reason somewhere.
        print(f"[backup-log] unable to write to {BACKUP_LOG_FILE}: {exc} :: {entry}")


@dataclass
class BackupRecord:
    name: str
    path: Path
    size: int
    created_at: str


class DatabaseBackupManager:
    def __init__(self) -> None:
        self.backup_dir = BACKUP_DIR
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.db_url = _normalize_url(os.getenv("DATABASE_URL") or DATABASE_URL)
        if not self.db_url:
            raise RuntimeError("DATABASE_URL is required for backups")

    def run_backup(self, label: Optional[str] = None) -> BackupRecord:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_label = ""
        if label:
            safe_label = "_" + "".join(ch for ch in label if ch.isalnum() or ch in ("-", "_")).strip("_")[:32]
        filename = f"backup_{timestamp}{safe_label}.dump"
        dest = self.backup_dir / filename
        cmd = [
            PG_DUMP_PATH,
            "-Fc",
            f"--dbname={self.db_url}",
            "-f",
            str(dest),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)  # nosec B603
            _secure_path(dest, 0o600)
            encrypted_path = _encrypt_file(dest)
            filename = encrypted_path.name
            dest = encrypted_path
            _append_log(f"Backup created: {filename}")
        except subprocess.CalledProcessError as exc:
            err = exc.stderr.decode() if exc.stderr else str(exc)
            _append_log(f"Backup failed: {filename} -> {err}")
            raise RuntimeError(f"pg_dump failed: {err}") from exc
        record = BackupRecord(
            name=filename,
            path=dest,
            size=dest.stat().st_size,
            created_at=_now_iso(),
        )
        self.purge_older(hours=backup_retention_hours())
        return record

    def _backup_files(self) -> List[Path]:
        files: List[Path] = []
        for pattern in ("backup_*.dump.enc", "backup_*.dump", "backup_*.sql"):
            files.extend(self.backup_dir.glob(pattern))
        return files

    @staticmethod
    def extract_label(name: str) -> Optional[str]:
        base = Path(name).name
        if base.endswith(".enc"):
            base = base[:-4]
        if base.endswith(".dump"):
            base = base[:-5]
        if base.endswith(".sql"):
            base = base[:-4]
        if not base.startswith("backup_"):
            return None
        rest = base[len("backup_") :]
        parts = rest.split("_", 1)
        if len(parts) == 2:
            return parts[1] or None
        return None

    def serialize_record(self, rec: BackupRecord) -> dict:
        label = self.extract_label(rec.name)
        return {
            "name": rec.name,
            "size": rec.size,
            "created_at": rec.created_at,
            "label": label or "scheduled",
        }

    def list_backups(self) -> List[BackupRecord]:
        items: List[BackupRecord] = []
        for file in sorted(self._backup_files(), key=lambda p: p.stat().st_mtime, reverse=True):
            stat = file.stat()
            items.append(
                BackupRecord(
                    name=file.name,
                    path=file,
                    size=stat.st_size,
                    created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                )
            )
        return items

    def purge_older(self, hours: float) -> None:
        if hours <= 0:
            return
        cutoff = time.time() - hours * 3600
        for file in self._backup_files():
            if file.stat().st_mtime < cutoff:
                try:
                    file.unlink()
                except Exception as exc:
                    _debug_suppressed("suppressed exception in backups.py:319", exc)

    def delete_backup(self, filename: str) -> None:
        target = self.backup_dir / filename
        if target.exists() and target.is_file():
            target.unlink()
            _append_log(f"Backup deleted: {filename}")
        else:
            raise FileNotFoundError("Backup not found")

    def restore_backup(self, payload: bytes, encryption_key: Optional[str] = None) -> None:
        global _last_restore_epoch
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        custom_dump = self.backup_dir / f"restore_{timestamp}.dump"
        raw_sql = self.backup_dir / f"restore_{timestamp}.sql"
        filtered_sql = self.backup_dir / f"restore_{timestamp}.filtered.sql"
        key_override = (encryption_key or "").strip() or None
        with _restore_lock:
            now = time.time()
            if (
                RESTORE_COOLDOWN_SECONDS > 0
                and _last_restore_epoch is not None
                and now - _last_restore_epoch < RESTORE_COOLDOWN_SECONDS
            ):
                wait = int(RESTORE_COOLDOWN_SECONDS - (now - _last_restore_epoch))
                raise RuntimeError(f"restore throttled; try again in {max(wait, 1)}s")
            _last_restore_epoch = now
            env = os.environ.copy()
            try:
                parsed = urlparse(self.db_url)
                if parsed.password and "PGPASSWORD" not in env:
                    env["PGPASSWORD"] = parsed.password
                env.setdefault("PAGER", "cat")
                app_name = f"restore/{timestamp}"
                env["PGAPPNAME"] = app_name
            except Exception:
                app_name = "restore"
            temp_payload = self.backup_dir / f"restore_{timestamp}.payload"
            temp_payload.write_bytes(payload)
            _secure_path(temp_payload, 0o600)
            try:
                requires_encrypted = RESTORE_REQUIRE_ENCRYPTED
                is_encrypted = _is_encrypted_file(temp_payload)
                if requires_encrypted and not is_encrypted:
                    raise RuntimeError("Encrypted backup required for restore")
                if is_encrypted:
                    _decrypt_file(temp_payload, custom_dump, key_override)
                    temp_payload.unlink(missing_ok=True)
                else:
                    if custom_dump.exists():
                        custom_dump.unlink()
                    temp_payload.rename(custom_dump)
                    _secure_path(custom_dump, 0o600)
            except Exception:
                temp_payload.unlink(missing_ok=True)
                raise
            _append_log(
                f"Restore started (size={len(payload)} bytes) "
                f"-> {custom_dump.name}"
            )
            killer_stop: Optional[threading.Event] = None
            killer_thread: Optional[threading.Thread] = None
            try:
                if RESTORE_TERMINATE_CONNECTIONS:
                    killer_stop = threading.Event()
                    killer_thread = threading.Thread(
                        target=self._terminate_sessions_loop,
                        args=(killer_stop, app_name),
                        daemon=True,
                    )
                    killer_thread.start()
                cmd_dump = [
                    PG_RESTORE_PATH,
                    "--no-owner",
                    "--no-privileges",
                    "--clean",
                    "--if-exists",
                    "-f",
                    str(raw_sql),
                    str(custom_dump),
                ]
                subprocess.run(  # nosec B603
                    cmd_dump,
                    check=True,
                    capture_output=True,
                    env=env,
                    stdin=subprocess.DEVNULL,
                )
                _append_log(f"pg_restore completed -> {raw_sql.name}")

                with raw_sql.open("r", encoding="utf-8", errors="replace") as src, filtered_sql.open("w", encoding="utf-8") as dst:
                    for line in src:
                        if line.strip().lower().startswith("set transaction_timeout"):
                            continue
                        dst.write(line)
                _append_log(f"Filtered SQL written -> {filtered_sql.name}")

                cmd_psql = [
                    PSQL_PATH,
                    "--single-transaction",
                    "--set",
                    "ON_ERROR_STOP=on",
                    "-f",
                    str(filtered_sql),
                    self.db_url,
                ]
                _append_log(f"psql starting -> {filtered_sql.name}")
                subprocess.run(  # nosec B603
                    cmd_psql,
                    check=True,
                    capture_output=True,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    timeout=RESTORE_TIMEOUT_SECONDS,
                )
                _append_log("Restore completed successfully.")
                _last_restore_epoch = time.time()
            except subprocess.TimeoutExpired as exc:
                _append_log(f"Restore failed: psql timed out after {RESTORE_TIMEOUT_SECONDS}s")
                raise RuntimeError(f"restore timed out after {RESTORE_TIMEOUT_SECONDS}s") from exc
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr.decode(errors="ignore") if exc.stderr else ""
                stdout = exc.stdout.decode(errors="ignore") if exc.stdout else ""
                details = stderr or stdout or str(exc)
                _append_log(f"Restore failed: {details}")
                raise RuntimeError(f"restore command failed: {details}") from exc
            except Exception as exc:
                _append_log(f"Restore failed: {exc}")
                raise RuntimeError(f"restore failed: {exc}") from exc
            finally:
                if killer_stop and killer_thread:
                    try:
                        killer_stop.set()
                        killer_thread.join(timeout=5)
                    except Exception as exc:
                        _debug_suppressed("suppressed exception in backups.py:457", exc)
                for path in (custom_dump, raw_sql, filtered_sql):
                    try:
                        path.unlink()
                    except Exception as exc:
                        if path.exists():
                            _append_log(f"Cleanup failed for {path.name}: {exc}")

    def _terminate_sessions_loop(self, stop_event: threading.Event, app_name: str) -> None:
        """Repeatedly terminates other connections to avoid lock waits."""
        if not self.db_url.startswith("postgresql"):
            return
        while not stop_event.is_set():
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text(
                            """
                            SELECT pg_terminate_backend(pid)
                              FROM pg_stat_activity
                             WHERE datname = current_database()
                               AND pid <> pg_backend_pid()
                               AND application_name <> :app_name
                            """
                        ),
                        {"app_name": app_name},
                    )
            except Exception as exc:
                _append_log(f"Session terminator error: {exc}")
                time.sleep(SESSION_KILL_INTERVAL)
                continue
            stop_event.wait(SESSION_KILL_INTERVAL)


def start_backup_scheduler() -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    if not backup_automatic_enabled():
        print("[backup scheduler] skipped: automatic backups disabled in System settings")
        return
    health = backup_encryption_health()
    if health.get("required") and not health.get("configured"):
        print(f"[backup scheduler] skipped: {health.get('warning') or 'backup encryption is not configured'}")
        return
    if not _acquire_backup_scheduler_lock():
        print("[backup scheduler] another process holds the scheduler lock; skipping start")
        return
    _scheduler_started = True

    def _worker():
        mgr = DatabaseBackupManager()
        interval_seconds = backup_interval_hours() * 3600
        next_run_at = time.time()
        last_epoch = _last_scheduled_backup_epoch(mgr)
        if last_epoch:
            next_run_at = max(next_run_at, last_epoch + interval_seconds)
        while True:
            now = time.time()
            delay = next_run_at - now
            if delay > 0:
                time.sleep(min(delay, 60))
                continue
            try:
                mgr.run_backup(label="scheduled")
            except Exception as exc:
                print(f"[backup scheduler] backup failed: {exc}")
            finally:
                interval_seconds = backup_interval_hours() * 3600
                next_run_at = time.time() + interval_seconds

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
def _secure_path(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except Exception as exc:
        _debug_suppressed("suppressed exception in backups.py:527", exc)


_secure_path(BACKUP_DIR, 0o700)
_secure_path(BACKUP_LOG_FILE.parent, 0o700)


def _derive_key_material(*args, **kwargs):
    from .backup_crypto import _derive_key_material as impl
    return impl(*args, **kwargs)


def _get_encryption_keys(*args, **kwargs):
    from .backup_crypto import _get_encryption_keys as impl
    return impl(*args, **kwargs)


def backup_encryption_health(*args, **kwargs):
    from .backup_crypto import backup_encryption_health as impl
    return impl(*args, **kwargs)


def _encrypt_file(*args, **kwargs):
    from .backup_crypto import _encrypt_file as impl
    return impl(*args, **kwargs)


def _is_encrypted_file(*args, **kwargs):
    from .backup_crypto import _is_encrypted_file as impl
    return impl(*args, **kwargs)


def _decrypt_file(*args, **kwargs):
    from .backup_crypto import _decrypt_file as impl
    return impl(*args, **kwargs)


def _sys_admin_emails() -> list[str]:
    db = SessionLocal()
    try:
        rows = (
            db.query(models.User.email)
            .filter(
                or_(
                    models.User.role == "sys_admin",
                    models.User.is_admin.is_(True),
                ),
                models.User.email.isnot(None),
            )
            .all()
        )
        emails = []
        for (email,) in rows:
            addr = (email or "").strip()
            if addr:
                emails.append(addr)
        return emails
    except Exception:
        return []
    finally:
        db.close()


def notify_missing_backup_key() -> None:
    """
    Sends a one-time email to sys admins when encrypted backups are required
    but no valid backup encryption key is available.
    """
    global _missing_key_alerted
    if _missing_key_alerted:
        return
    health = backup_encryption_health()
    if not health.get("required") or health.get("configured"):
        return
    if not mail_provider_ready():
        return
    recipients = _sys_admin_emails()
    body = (
        "Automatic backups cannot run because no valid backup encryption key is available. "
        "Container deployments generate and persist one automatically; restart the backend "
        "to retry key bootstrap. For non-container deployments, configure BACKUP_ENCRYPTION_KEY "
        "or explicitly allow plaintext backups."
    )
    if recipients:
        try:
            send_email(
                recipients=recipients,
                subject=branded_subject("Backup encryption key missing"),
                body=body,
            )
            _missing_key_alerted = True
        except Exception as exc:
            print(f"[backup] unable to send missing-key alert: {exc}")
    try:
        _send_teams_notification(
            "backup_key_missing",
            {
                "message": body,
            },
        )
        _missing_key_alerted = True
    except Exception as exc:
        print(f"[backup] unable to send teams missing-key alert: {exc}")
