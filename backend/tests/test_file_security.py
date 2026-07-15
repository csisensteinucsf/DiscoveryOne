import io
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from fastapi import HTTPException

from app import file_security


def _configure_scanner(monkeypatch, *, allow_insecure_dev: bool) -> None:
    monkeypatch.setattr(file_security, "_ALLOW_INSECURE_DEV", allow_insecure_dev)
    monkeypatch.setattr(file_security, "_SCAN_DISABLED", False)
    monkeypatch.setattr(file_security, "_SCANNER_UNAVAILABLE", False)
    monkeypatch.setattr(file_security, "_SCANNER_RESOLVED", True)
    monkeypatch.setattr(file_security, "_SCANNER_CACHE", None)
    monkeypatch.setattr(file_security, "_CLAM_HOST", "clamav")
    monkeypatch.setattr(file_security, "_CLAM_PORT", 3310)
    monkeypatch.setattr(file_security, "_resolve_scanner", lambda: None)


def test_scan_payload_allows_unscanned_upload_in_insecure_dev(monkeypatch):
    _configure_scanner(monkeypatch, allow_insecure_dev=True)

    def _raise_unreachable(*_args, **_kwargs):
        raise OSError("scanner offline")

    monkeypatch.setattr(file_security.socket, "create_connection", _raise_unreachable)

    assert file_security.scan_payload(b"demo payload", "evidence.pdf") is None


def test_scan_payload_blocks_upload_when_scanner_unreachable_in_normal_mode(monkeypatch):
    _configure_scanner(monkeypatch, allow_insecure_dev=False)

    def _raise_unreachable(*_args, **_kwargs):
        raise OSError("scanner offline")

    monkeypatch.setattr(file_security.socket, "create_connection", _raise_unreachable)

    with pytest.raises(HTTPException) as exc_info:
        file_security.scan_payload(b"demo payload", "evidence.pdf")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Malware scanner unavailable"


def test_check_upload_scanner_ready_reports_unreachable_clamav(monkeypatch):
    _configure_scanner(monkeypatch, allow_insecure_dev=False)

    def _raise_unreachable(*_args, **_kwargs):
        raise OSError("scanner offline")

    monkeypatch.setattr(file_security.socket, "create_connection", _raise_unreachable)

    with pytest.raises(RuntimeError, match="ClamAV daemon unreachable"):
        file_security.check_upload_scanner_ready()


def _office_zip(*members: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types />")
        for member in members:
            zf.writestr(member, "")
    return buf.getvalue()


def test_validate_attachment_bytes_allows_note_document_types():
    allowed = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }

    assert file_security.validate_attachment_bytes(b"%PDF-1.7\n", "evidence.pdf", max_bytes=1024, allowed_mime_types=allowed) == "application/pdf"
    assert file_security.validate_attachment_bytes(
        _office_zip("word/document.xml"),
        "memo.docx",
        max_bytes=1024,
        allowed_mime_types=allowed,
    ) == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert file_security.validate_attachment_bytes(
        _office_zip("xl/workbook.xml"),
        "tracking.xlsx",
        max_bytes=1024,
        allowed_mime_types=allowed,
    ) == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    ole_payload = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 32
    assert file_security.validate_attachment_bytes(ole_payload, "legacy.doc", max_bytes=1024, allowed_mime_types=allowed) == "application/msword"
    assert file_security.validate_attachment_bytes(ole_payload, "legacy.xls", max_bytes=1024, allowed_mime_types=allowed) == "application/vnd.ms-excel"


def test_scan_payload_retries_clamav_stream_until_available(monkeypatch):
    _configure_scanner(monkeypatch, allow_insecure_dev=False)
    monkeypatch.setattr(file_security, "_SCAN_CONNECT_RETRIES", 2)
    monkeypatch.setattr(file_security, "_SCAN_CONNECT_RETRY_DELAY", 0)
    attempts = {"count": 0}

    class _Socket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def settimeout(self, _timeout):
            return None

        def sendall(self, _payload):
            return None

        def recv(self, _size):
            return b"stream: OK\n"

    def _connect(*_args, **_kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OSError("scanner warming up")
        return _Socket()

    monkeypatch.setattr(file_security.socket, "create_connection", _connect)

    assert file_security.scan_payload(b"demo payload", "evidence.pdf") is None
    assert attempts["count"] == 2


def test_get_upload_scanner_status_reports_signature_freshness(monkeypatch):
    monkeypatch.setattr(file_security, "_SCAN_DISABLED", False)
    monkeypatch.setattr(file_security, "_CLAM_HOST", "clamav")
    monkeypatch.setattr(file_security, "_CLAM_SIGNATURE_MAX_AGE_HOURS", 72)
    monkeypatch.setattr(file_security, "check_upload_scanner_ready", lambda: None)
    signature_date = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%a %b %d %H:%M:%S %Y")
    monkeypatch.setattr(
        file_security,
        "_clamav_command",
        lambda command: f"ClamAV 1.4.0/27613/{signature_date}\n".encode(),
    )

    status = file_security.get_upload_scanner_status()

    assert status["ready"] is True
    assert status["engine"] == "ClamAV 1.4.0"
    assert status["signature_version"] == 27613
    assert status["definitions_current"] is True
