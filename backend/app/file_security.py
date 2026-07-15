from __future__ import annotations

import io
import logging
import os
import re
import shlex
import shutil
import subprocess  # nosec B404
import tempfile
import time
from pathlib import Path
from typing import Iterable, Optional
import zipfile
import socket
import struct
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from .notifications import notify_malware_upload_detected
from .safe_log import debug_suppressed as _debug_suppressed

logger = logging.getLogger("app.file_security")

_ALLOW_INSECURE_DEV = (os.getenv("ALLOW_INSECURE_DEV") or "").strip().lower() in {"1", "true", "yes", "on"}
_SCAN_DISABLED = (os.getenv("UPLOAD_SCAN_DISABLE") or "").lower() in {"1", "true", "yes"}
_SCAN_TIMEOUT = int(os.getenv("UPLOAD_SCAN_TIMEOUT", "30"))
_SCAN_CONNECT_RETRIES = max(1, int(os.getenv("UPLOAD_SCAN_CONNECT_RETRIES", "3")))
_SCAN_CONNECT_RETRY_DELAY = float(os.getenv("UPLOAD_SCAN_CONNECT_RETRY_DELAY", "1"))
_SCAN_COMMAND_RAW = os.getenv("UPLOAD_SCAN_CMD")
_SCANNER_CACHE: Optional[list[str]] = None
_SCANNER_RESOLVED = False
_SCANNER_UNAVAILABLE = False
_STREAM_CHUNK = 16 * 1024
_CLAM_HOST = os.getenv("CLAMAV_HOST", "clamav")
_CLAM_PORT = int(os.getenv("CLAMAV_PORT", "3310"))
_CLAM_SIGNATURE_MAX_AGE_HOURS = int(os.getenv("CLAMAV_SIGNATURE_MAX_AGE_HOURS", "72"))
_OLE_COMPOUND_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _allow_unscanned_upload(reason: str, *, filename: Optional[str] = None) -> bool:
    if not _ALLOW_INSECURE_DEV:
        return False
    label = filename or "upload"
    logger.warning(
        "Upload scanner unavailable for %s; allowing upload without scanning because ALLOW_INSECURE_DEV=1 (%s)",
        label,
        reason,
    )
    return True


def _resolve_scanner() -> Optional[list[str]]:
    global _SCANNER_CACHE, _SCANNER_RESOLVED, _SCANNER_UNAVAILABLE
    if _SCANNER_RESOLVED:
        return _SCANNER_CACHE
    _SCANNER_RESOLVED = True
    _SCANNER_UNAVAILABLE = False
    if _SCAN_DISABLED:
        logger.info("Upload scanning disabled via UPLOAD_SCAN_DISABLE")
        _SCANNER_CACHE = None
        return None
    candidates: Iterable[list[str]]
    if _SCAN_COMMAND_RAW:
        parts = shlex.split(_SCAN_COMMAND_RAW)
        if not parts:
            logger.warning("UPLOAD_SCAN_CMD was provided but empty")
            _SCANNER_CACHE = None
            return None
        if not shutil.which(parts[0]):
            logger.warning("Upload scanner command %s not found on PATH", parts[0])
            _SCANNER_CACHE = None
            return None
        candidates = [parts]
    else:
        candidates = [[cmd, "--no-summary"] for cmd in ("clamdscan", "clamscan")]
    for cmd in candidates:
        path = shutil.which(cmd[0])
        if path:
            resolved = cmd[:]
            resolved[0] = path
            _SCANNER_CACHE = resolved
            logger.info("Using upload scanner command: %s", " ".join(resolved))
            return _SCANNER_CACHE
    if not (_CLAM_HOST or "").strip():
        logger.error("No malware scanner command or daemon configured; uploads blocked")
        _SCANNER_UNAVAILABLE = True
        _SCANNER_CACHE = None
        return None
    logger.info("Scanner CLI not present; falling back to ClamAV INSTREAM")
    _SCANNER_CACHE = None
    return None


def check_upload_scanner_ready() -> None:
    """
    Quick readiness check so we can warn at startup if uploads will be rejected
    due to missing AV configuration.
    """
    if _SCAN_DISABLED:
        logger.warning("Upload scanning disabled via UPLOAD_SCAN_DISABLE")
        return
    cmd = _resolve_scanner()
    if _SCANNER_UNAVAILABLE:
        raise RuntimeError("Upload scanning unavailable: no scanner command and no ClamAV host configured")
    if cmd:
        logger.info("Upload scanner ready via command: %s", " ".join(cmd))
        return
    try:
        with socket.create_connection((_CLAM_HOST, _CLAM_PORT), timeout=_SCAN_TIMEOUT):
            logger.info("Upload scanner ready via ClamAV INSTREAM at %s:%s", _CLAM_HOST, _CLAM_PORT)
    except (socket.timeout, ConnectionError, OSError) as exc:
        detail = f"ClamAV daemon unreachable at {_CLAM_HOST}:{_CLAM_PORT}: {exc}"
        if _allow_unscanned_upload(detail):
            return
        raise RuntimeError(detail) from exc


def get_upload_scanner_status() -> dict:
    """
    Return readiness plus ClamAV signature metadata for admin health checks.

    The official ClamAV container runs FreshClam in the same container by
    default; querying VERSION lets us expose whether clamd has loaded recent
    signatures instead of assuming the updater is healthy.
    """
    status = {
        "ready": True,
        "error": None,
        "disabled": _SCAN_DISABLED,
        "engine": None,
        "signature_version": None,
        "signature_date": None,
        "signature_age_hours": None,
        "signature_max_age_hours": _CLAM_SIGNATURE_MAX_AGE_HOURS,
        "definitions_current": None,
    }
    try:
        check_upload_scanner_ready()
    except Exception as exc:
        status["ready"] = False
        status["error"] = str(exc)
        return status
    if _SCAN_DISABLED or not (_CLAM_HOST or "").strip():
        return status
    try:
        version = _clamav_command("VERSION").decode(errors="ignore").strip()
    except Exception as exc:
        status["error"] = f"Unable to query ClamAV VERSION: {exc}"
        return status
    parts = version.split("/")
    if parts:
        status["engine"] = parts[0].strip() or None
    if len(parts) >= 2 and parts[1].strip().isdigit():
        status["signature_version"] = int(parts[1].strip())
    if len(parts) >= 3:
        signature_date_text = "/".join(parts[2:]).strip()
        status["signature_date"] = signature_date_text or None
        try:
            signature_date = datetime.strptime(signature_date_text, "%a %b %d %H:%M:%S %Y").replace(tzinfo=timezone.utc)
            age_hours = max(0.0, (datetime.now(timezone.utc) - signature_date).total_seconds() / 3600)
            status["signature_age_hours"] = round(age_hours, 2)
            status["definitions_current"] = age_hours <= _CLAM_SIGNATURE_MAX_AGE_HOURS
        except ValueError:
            status["definitions_current"] = None
    return status


def scan_payload(payload: bytes, filename: str, *, request: Optional[Request] = None, actor: Optional[object] = None) -> None:
    """Scan payload bytes with the configured AV engine."""
    if not payload or _SCAN_DISABLED:
        return
    cmd = _resolve_scanner()
    if _SCANNER_UNAVAILABLE:
        if _allow_unscanned_upload("no scanner command configured", filename=filename):
            return
        raise HTTPException(status_code=503, detail="Malware scanner unavailable")
    if cmd:
        _scan_with_command(cmd, payload, filename, request=request, actor=actor)
        return
    _scan_with_stream(payload, filename, request=request, actor=actor)


def _alert_detection(filename: str, detail: str, request: Optional[Request], actor: Optional[object]) -> None:
    try:
        notify_malware_upload_detected(filename=filename, detail=detail, actor=actor, request=request)
    except Exception as exc:
        logger.error("Failed to send malware detection alert for %s: %s", filename, exc)
    try:
        from .database import SessionLocal
        from .audit import log_event

        path = None
        try:
            if request is not None:
                path = str(getattr(getattr(request, "url", None), "path", None) or "")
        except Exception:
            path = None

        details = {
            "filename": filename,
            "scanner_detail": (detail or "")[:2000] or None,
            "path": path or None,
        }
        if path:
            try:
                m = re.search(r"/cases/(\\d+)", path)
                if m:
                    details["case_id"] = int(m.group(1))
            except Exception as exc:
                _debug_suppressed("suppressed exception in file_security.py:133", exc)
            try:
                m = re.search(r"/custodians/(\\d+)", path)
                if m:
                    details["custodian_id"] = int(m.group(1))
            except Exception as exc:
                _debug_suppressed("suppressed exception in file_security.py:139", exc)

        db = SessionLocal()
        try:
            log_event(
                db,
                action="malware_upload_detected",
                actor_id=getattr(actor, "id", None),
                target_type="upload",
                target_id=None,
                details=details,
                request=request,
            )
        finally:
            try:
                db.close()
            except Exception as exc:
                _debug_suppressed("suppressed exception in file_security.py:156", exc)
    except Exception as exc:
        # never block primary flow on audit failure
        _debug_suppressed("suppressed exception in file_security.py:158", exc)


def _audit_scan_result(
    filename: str,
    verdict: str,
    detail: str,
    request: Optional[Request],
    actor: Optional[object],
) -> None:
    try:
        from .database import SessionLocal
        from .audit import log_event

        path = None
        try:
            if request is not None:
                path = str(getattr(getattr(request, "url", None), "path", None) or "")
        except Exception:
            path = None

        db = SessionLocal()
        try:
            log_event(
                db,
                action="upload_scan",
                actor_id=getattr(actor, "id", None),
                target_type="upload",
                target_id=None,
                details={
                    "filename": filename,
                    "verdict": verdict,
                    "scanner_detail": (detail or "")[:2000] or None,
                    "path": path or None,
                },
                request=request,
            )
        finally:
            try:
                db.close()
            except Exception as exc:
                _debug_suppressed("suppressed exception in file_security.py:207", exc)
    except Exception as exc:
        _debug_suppressed("suppressed exception in file_security.py:209", exc)


def _scan_with_command(cmd: list[str], payload: bytes, filename: str, *, request: Optional[Request], actor: Optional[object]) -> None:
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(payload)
            tmp_path = tmp.name
        proc = subprocess.run(  # nosec B603
            cmd + [tmp_path],
            capture_output=True,
            text=True,
            timeout=_SCAN_TIMEOUT,
        )
        if proc.returncode == 1:
            detail = proc.stderr or proc.stdout or "threat detected"
            logger.warning("Scanner flagged %s: %s", filename, detail)
            _audit_scan_result(filename, "malicious", detail, request, actor)
            _alert_detection(filename, detail, request, actor)
            raise HTTPException(status_code=400, detail="Upload rejected by malware scanner")
        if proc.returncode not in (0,):
            if _allow_unscanned_upload(f"scanner command exited with code {proc.returncode}", filename=filename):
                return
            logger.error("Scanner failed for %s (code %s): %s", filename, proc.returncode, proc.stderr or proc.stdout)
            raise HTTPException(status_code=500, detail="Unable to scan uploaded file")
        _audit_scan_result(filename, "clean", proc.stdout or "OK", request, actor)
    except subprocess.TimeoutExpired:
        if _allow_unscanned_upload(f"scanner command timed out after {_SCAN_TIMEOUT}s", filename=filename):
            return
        logger.error("Scanner timed out after %ss while scanning %s", _SCAN_TIMEOUT, filename)
        raise HTTPException(status_code=500, detail="Malware scan timed out")
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass


def _scan_with_stream(payload: bytes, filename: str, *, request: Optional[Request], actor: Optional[object]) -> None:
    if _SCAN_DISABLED:
        return
    last_exc: Optional[BaseException] = None
    for attempt in range(1, _SCAN_CONNECT_RETRIES + 1):
        try:
            response = _stream_payload_to_clamav(payload)
            break
        except (socket.timeout, ConnectionError, OSError) as exc:
            last_exc = exc
            if attempt < _SCAN_CONNECT_RETRIES:
                logger.warning(
                    "Unable to contact ClamAV daemon at %s:%s while scanning %s (attempt %s/%s): %s",
                    _CLAM_HOST,
                    _CLAM_PORT,
                    filename,
                    attempt,
                    _SCAN_CONNECT_RETRIES,
                    exc,
                )
                time.sleep(_SCAN_CONNECT_RETRY_DELAY)
                continue
            if _allow_unscanned_upload(f"ClamAV daemon unreachable at {_CLAM_HOST}:{_CLAM_PORT}: {exc}", filename=filename):
                return
            logger.error("Unable to contact ClamAV daemon at %s:%s: %s", _CLAM_HOST, _CLAM_PORT, exc)
            raise HTTPException(status_code=500, detail="Malware scanner unavailable")
    else:
        if _allow_unscanned_upload(f"ClamAV daemon unreachable at {_CLAM_HOST}:{_CLAM_PORT}: {last_exc}", filename=filename):
            return
        raise HTTPException(status_code=500, detail="Malware scanner unavailable")

    text = response.decode(errors="ignore").strip()
    if not text:
        if _allow_unscanned_upload("ClamAV daemon returned an empty response", filename=filename):
            return
        logger.error("ClamAV daemon returned no verdict for %s", filename)
        raise HTTPException(status_code=500, detail="Scanner returned an empty response")
    if "FOUND" in text.upper():
        logger.warning("Scanner flagged %s: %s", filename, text)
        _audit_scan_result(filename, "malicious", text, request, actor)
        _alert_detection(filename, text, request, actor)
        raise HTTPException(status_code=400, detail="Upload rejected by malware scanner")
    if "OK" not in text.upper():
        if _allow_unscanned_upload(f"unexpected scanner response: {text}", filename=filename):
            return
        logger.error("Unexpected scanner response for %s: %s", filename, text)
        raise HTTPException(status_code=500, detail="Scanner error")
    _audit_scan_result(filename, "clean", text, request, actor)


def _stream_payload_to_clamav(payload: bytes) -> bytes:
    with socket.create_connection((_CLAM_HOST, _CLAM_PORT), timeout=_SCAN_TIMEOUT) as sock:
        sock.settimeout(_SCAN_TIMEOUT)
        sock.sendall(b"zINSTREAM\0")
        mv = memoryview(payload)
        for offset in range(0, len(mv), _STREAM_CHUNK):
            chunk = mv[offset : offset + _STREAM_CHUNK]
            sock.sendall(struct.pack(">I", len(chunk)))
            sock.sendall(chunk)
        sock.sendall(struct.pack(">I", 0))
        response = b""
        while True:
            data = sock.recv(4096)
            if not data:
                break
            response += data
            if b"\n" in response:
                break
        return response


def _clamav_command(command: str) -> bytes:
    with socket.create_connection((_CLAM_HOST, _CLAM_PORT), timeout=_SCAN_TIMEOUT) as sock:
        sock.settimeout(_SCAN_TIMEOUT)
        sock.sendall(f"z{command}\0".encode("ascii"))
        response = b""
        while True:
            data = sock.recv(4096)
            if not data:
                break
            response += data
            if b"\n" in response:
                break
        return response


def scan_file(path: Path, filename: str) -> None:
    """
    Convenience helper to scan a saved file without reimplementing the
    payload logic in every upload handler.
    """
    if not path or not path.exists():
        raise HTTPException(status_code=400, detail="Uploaded file is missing")
    try:
        data = path.read_bytes()
    except Exception as exc:
        logger.exception("Unable to read uploaded file: %s", filename)
        raise HTTPException(status_code=400, detail="Unable to read uploaded file") from exc
    scan_payload(data, filename)


def sniff_mime(payload: bytes) -> str:
    if not payload:
        return "application/octet-stream"
    head = payload[:8]
    if payload[:5] == b"%PDF-":
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp"
    if head[:2] == b"PK":
        if _looks_like_docx(payload):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if _looks_like_xlsx(payload):
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return "application/zip"
    if _looks_like_text(payload):
        return "text/plain"
    return "application/octet-stream"


def _looks_like_docx(payload: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            if not names:
                return False
            return "[Content_Types].xml" in names and any(name.startswith("word/") for name in names)
    except Exception:
        return False


def _looks_like_xlsx(payload: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            if not names:
                return False
            return "[Content_Types].xml" in names and any(name.startswith("xl/") for name in names)
    except Exception:
        return False


def _zip_contains_xlsx(payload: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".xlsx"):
                    return True
    except Exception:
        return False
    return False


def _looks_like_text(payload: bytes) -> bool:
    if not payload:
        return True
    sample = payload[:4096]
    text_bytes = set(range(32, 127))
    text_bytes.update({9, 10, 13})
    weird = sum(1 for b in sample if b not in text_bytes)
    return weird / max(1, len(sample)) < 0.1


def validate_image_bytes(
    payload: bytes,
    *,
    max_bytes: int,
    allowed_mime_types: Optional[Iterable[str]] = None,
    empty_detail: str = "Uploaded file is empty",
    size_detail: str = "File exceeds size limit",
    unsupported_detail: str = "Unsupported image format",
) -> str:
    if not payload:
        raise HTTPException(status_code=400, detail=empty_detail)
    if len(payload) > max_bytes:
        raise HTTPException(status_code=413, detail=size_detail)
    mime = sniff_mime(payload)
    allowed = set(allowed_mime_types or {"image/png", "image/jpeg"})
    if mime not in allowed:
        raise HTTPException(status_code=415, detail=unsupported_detail)
    return mime


def validate_attachment_bytes(
    payload: bytes,
    filename: Optional[str],
    *,
    max_bytes: int,
    allowed_mime_types: Optional[Iterable[str]] = None,
    empty_detail: str = "Uploaded file is empty",
    size_detail: str = "File exceeds size limit",
    unsupported_detail: str = "Unsupported attachment format",
) -> str:
    if not payload:
        raise HTTPException(status_code=400, detail=empty_detail)
    if len(payload) > max_bytes:
        raise HTTPException(status_code=413, detail=size_detail)

    allowed = set(allowed_mime_types or set())
    mime = sniff_mime(payload)
    if mime in allowed:
        return mime

    ext = (Path(filename or "").suffix or "").strip().lower()
    if ext == ".doc" and payload[:8] == _OLE_COMPOUND_MAGIC and "application/msword" in allowed:
        return "application/msword"
    if ext == ".xls" and payload[:8] == _OLE_COMPOUND_MAGIC and "application/vnd.ms-excel" in allowed:
        return "application/vnd.ms-excel"

    raise HTTPException(status_code=415, detail=unsupported_detail)


def validate_logo_bytes(payload: bytes, *, max_bytes: int) -> str:
    return validate_image_bytes(
        payload,
        max_bytes=max_bytes,
        allowed_mime_types={"image/png", "image/jpeg"},
        empty_detail="Uploaded file is empty",
        size_detail="Logo exceeds size limit",
        unsupported_detail="Unsupported logo format",
    )


def validate_case_import_bytes(payload: bytes, *, max_bytes: Optional[int] = None) -> str:
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if max_bytes and len(payload) > max_bytes:
        raise HTTPException(status_code=413, detail="Import file exceeds size limit")
    mime = sniff_mime(payload)
    if mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return mime
    if mime == "application/zip":
        if not _zip_contains_xlsx(payload):
            raise HTTPException(
                status_code=400,
                detail="Zip archive must contain at least one .xlsx workbook",
            )
        return mime
    raise HTTPException(status_code=415, detail="Unsupported file type; expected .xlsx or .zip archive")


def validate_csv_bytes(payload: bytes, *, max_bytes: Optional[int] = None) -> None:
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if max_bytes and len(payload) > max_bytes:
        raise HTTPException(status_code=413, detail="Uploaded file exceeds size limit")
    if b"\x00" in payload:
        raise HTTPException(status_code=400, detail="Binary data detected in uploaded file")
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Uploaded file must be UTF-8 encoded text")
    sniffed = sniff_mime(payload)
    if sniffed not in {"text/plain", "text/csv"}:
        raise HTTPException(status_code=415, detail="Unsupported attachment format; expected CSV/text")
