"""
backend/app/logging_setup.py

Rotating file logging with compression.
- Rolls over at LOG_MAX_MB (default 25 MB)
- Keeps LOG_BACKUP_COUNT compressed backups (default 20)
- Writes to LOG_DIR/LOG_FILE_NAME (default: /app/logs/app.log)
- Compresses rotated files to .gz
- Hooks root + uvicorn loggers
"""

import os
import gzip
import shutil
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .safe_log import debug_suppressed as _debug_suppressed

DEFAULT_DIR = os.getenv("LOG_DIR", "/app/logs")
DEFAULT_NAME = os.getenv("LOG_FILE_NAME", "app.log")
DEFAULT_MAX_MB = int(os.getenv("LOG_MAX_MB", os.getenv("AUDIT_LOG_MAX_MB", "25")))
DEFAULT_BACKUPS = int(os.getenv("LOG_BACKUP_COUNT", os.getenv("AUDIT_LOG_BACKUP_COUNT", "20")))
DEFAULT_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _make_handler(log_path: Path, max_mb: int, backups: int, *, compress: bool = True) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_mb * 1024 * 1024,
        backupCount=backups,
        encoding="utf-8",
        delay=True,  # create file lazily
    )

    # Name rotated files e.g., app.log.1.gz
    def namer(default_name: str) -> str:
        return default_name + ".gz"

    # Compress the rotated file
    def rotator(source: str, dest: str) -> None:
        with open(source, "rb") as f_in, gzip.open(dest, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        try:
            os.remove(source)
        except FileNotFoundError:
            pass

    if compress:
        handler.namer = namer
        handler.rotator = rotator

    fmt = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(process)d %(threadName)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(fmt)
    return handler


_TS_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
_DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s %(process)d %(threadName)s - %(message)s"


def _ensure_timestamp_formatter(handler: logging.Handler) -> None:
    """Force a formatter with timestamp on handlers that lack asctime."""
    try:
        fmt = handler.formatter
        has_asctime = fmt is not None and "%(asctime)" in fmt._fmt  # type: ignore[attr-defined]
    except Exception:
        has_asctime = False
    if not has_asctime:
        handler.setFormatter(logging.Formatter(fmt=_DEFAULT_FORMAT, datefmt=_TS_FORMAT))


def _rollover_if_oversized(handler: RotatingFileHandler) -> None:
    """Rotate immediately when an existing log file is already above maxBytes."""
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
        # Keep startup resilient even if rollover fails.
        _debug_suppressed("suppressed exception in logging_setup.py:90", exc)


def setup_file_logging(
    log_dir: str | None = None,
    log_name: str | None = None,
    max_mb: int | None = None,
    backups: int | None = None,
    level: str | int | None = None,
    *,
    compress: bool = True,
) -> None:
    """Idempotent setup. Safe to call multiple times."""
    dir_path = Path(log_dir or DEFAULT_DIR)
    file_name = log_name or DEFAULT_NAME
    max_mb = int(max_mb or DEFAULT_MAX_MB)
    backups = int(backups or DEFAULT_BACKUPS)
    level = level or DEFAULT_LEVEL

    _ensure_dir(dir_path)
    log_path = dir_path / file_name

    root = logging.getLogger()
    # Avoid duplicate handlers if called twice
    already = any(isinstance(h, RotatingFileHandler) and getattr(h, "_app_rotator", False) for h in root.handlers)
    if not already:
        handler = _make_handler(log_path, max_mb, backups, compress=compress)
        # mark to detect duplicates
        handler._app_rotator = True  # type: ignore[attr-defined]
        root.addHandler(handler)
        _rollover_if_oversized(handler)

    # Ensure all handlers have timestamped formatter (console + file)
    for h in list(root.handlers):
        _ensure_timestamp_formatter(h)
        if isinstance(h, RotatingFileHandler) and getattr(h, "_app_rotator", False):
            _rollover_if_oversized(h)

    # Set levels (keep console handlers intact)
    try:
        lvl = getattr(logging, str(level).upper(), logging.INFO)
    except Exception:
        lvl = logging.INFO
    root.setLevel(lvl)

    # Ensure uvicorn loggers propagate to root so they land in file
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.setLevel(lvl)
        lg.propagate = True
        for h in list(lg.handlers):
            _ensure_timestamp_formatter(h)

    # Optional: a dedicated audit logger, used by audit.log_event (future use)
    logging.getLogger("audit").setLevel(lvl)
