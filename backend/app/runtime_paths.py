from __future__ import annotations

import os
import tempfile
from pathlib import Path
from .safe_log import debug_suppressed as _debug_suppressed


def _default_runtime_dir() -> Path:
    explicit = (os.getenv("APP_RUNTIME_DIR") or "").strip()
    if explicit:
        return Path(explicit)
    if os.name == "nt":
        return Path(tempfile.gettempdir()) / "discoveryone"
    return Path("/app/run")


def runtime_dir() -> Path:
    path = _default_runtime_dir()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        _debug_suppressed("suppressed exception in runtime_paths.py:21", exc)
    return path


def runtime_file(filename: str) -> str:
    safe = (filename or "").strip().replace("/", "_").replace("\\", "_")
    if not safe:
        safe = "runtime.lock"
    return str(runtime_dir() / safe)
