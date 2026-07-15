"""Backup encryption and key validation helpers."""

from __future__ import annotations

import base64
import os
import shutil
from pathlib import Path
from typing import Optional, Tuple

from cryptography.hazmat.primitives import hashes, hmac
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .safe_log import debug_suppressed as _debug_suppressed

ALLOW_PLAINTEXT_BACKUPS = (os.getenv("ALLOW_PLAINTEXT_BACKUPS") or "").strip().lower() in {"1", "true", "yes", "on"}
_CHUNK_SIZE = 1024 * 1024
_MAGIC = b"BKP1"
_VERSION = b"\x01"
_IV_SIZE = 16
_MAC_SIZE = 32
_KEY_CACHE: Optional[Tuple[bytes, bytes]] = None


def _secure_path(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except Exception as exc:
        _debug_suppressed("suppressed exception in backup_crypto.py:secure_path", exc)


def _derive_key_material(source: bytes) -> Tuple[bytes, bytes]:
    def _derive(label: bytes) -> bytes:
        h = hashes.Hash(hashes.SHA256())
        h.update(source + label)
        return h.finalize()

    return _derive(b"enc"), _derive(b"mac")


def _get_encryption_keys(override: Optional[str] = None) -> Optional[Tuple[bytes, bytes]]:
    if override:
        try:
            decoded = base64.urlsafe_b64decode(override)
        except Exception as exc:
            raise RuntimeError("Encryption key must be base64-encoded") from exc
        if len(decoded) < 32:
            raise RuntimeError("Encryption key must decode to at least 32 bytes")
        return _derive_key_material(decoded)

    global _KEY_CACHE
    if _KEY_CACHE is not None:
        return _KEY_CACHE
    raw = (os.getenv("BACKUP_ENCRYPTION_KEY") or "").strip()
    if not raw:
        _KEY_CACHE = None
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw)
    except Exception as exc:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY must be base64-encoded") from exc
    if len(decoded) < 32:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY must decode to at least 32 bytes")
    _KEY_CACHE = _derive_key_material(decoded)
    return _KEY_CACHE


def backup_encryption_health() -> dict:
    """
    Returns metadata about the active backup encryption key so the UI
    can warn operators when encrypted backups are required but not configured.
    """
    status = {
        "required": not ALLOW_PLAINTEXT_BACKUPS,
        "configured": False,
        "warning": None,
    }
    raw = (os.getenv("BACKUP_ENCRYPTION_KEY") or "").strip()
    if not raw:
        if status["required"]:
            status["warning"] = "Backup encryption key is not configured. Container deployments generate and persist one automatically."
        return status
    try:
        decoded = base64.urlsafe_b64decode(raw)
    except Exception:
        status["warning"] = "Backup encryption key is not valid base64."
        return status
    if len(decoded) < 32:
        status["warning"] = "Backup encryption key must decode to at least 32 bytes."
        return status
    status["configured"] = True
    return status

