#!/usr/bin/env python3
"""
MSG/EML bulk converter with GUI/CLI entry points.

Features
--------
* Recursively scans an input directory for .msg and .eml files.
* Converts MSG files to standards-compliant EML (prefers the msgconvert
  command described in Convert MSG to EML.txt, but falls back to a pure
  Python implementation via extract_msg for portability).
* Renders both the email body and every attachment to individual PDFs.
  Attachments keep the same relative folder hierarchy and duplicate names
  are automatically deduplicated.
* Provides both a Tkinter GUI for non-technical use and a CLI for scripting.
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import queue
import shutil
import subprocess  # nosec B404
import sys
import textwrap
import threading
from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import format_datetime
from io import BytesIO
from pathlib import Path
from typing import Callable, Iterable, Optional

import extract_msg
from bs4 import BeautifulSoup
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Preformatted, SimpleDocTemplate, Spacer, Paragraph

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except Exception:  # pragma: no cover - tkinter might be missing in CLI environments
    tk = None
    filedialog = messagebox = ttk = None


Logger = Callable[[str], None]

TEXT_ATTACHMENT_EXTS = {
    ".txt",
    ".text",
    ".log",
    ".csv",
    ".json",
    ".xml",
    ".ini",
    ".cfg",
    ".rtf",
    ".md",
}
HTML_ATTACHMENT_EXTS = {".html", ".htm"}
IMAGE_ATTACHMENT_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff"}
PDF_EXT = ".pdf"
SUPPORTED_SUFFIXES = {".msg", ".eml"}
DEBUG = bool(os.environ.get("EMAIL2PDF_DEBUG"))
DEFAULT_FILENAME_LIMIT = 200
WINDOWS_FILENAME_LIMIT = 120


def noop_log(_: str) -> None:
    """Fallback logger."""


def sanitize_filename(name: str | None, default: str = "attachment", max_length: int | None = None) -> str:
    """Remove characters that are unsafe on Windows paths."""
    if not name:
        name = default
    cleaned = (
        name.replace("\x00", "")
        .replace("/", "_")
        .replace("\\", "_")
        .strip()
    )
    cleaned = "".join(ch if ch not in '<>:"|?*' else "_" for ch in cleaned)
    if not cleaned:
        cleaned = default
    limit = max_length or DEFAULT_FILENAME_LIMIT
    if limit > 0 and len(cleaned) > limit:
        stem, ext = os.path.splitext(cleaned)
        keep = max(1, limit - len(ext))
        cleaned = stem[:keep] + ext
    return cleaned


def ensure_binary_data(data, encoding: str = "utf-8") -> bytes:
    """Best effort conversion of arbitrary attachment payloads to bytes."""
    if data is None:
        return b""
    if isinstance(data, bytes):
        return data
    if isinstance(data, (bytearray, memoryview)):
        return bytes(data)
    if isinstance(data, str):
        return data.encode(encoding, errors="replace")
    if hasattr(data, "read"):
        return data.read()
    try:
        return bytes(data)
    except Exception:
        return str(data).encode(encoding, errors="replace")


def ensure_text(data, encoding: str = "utf-8") -> str:
    """Ensure payload is str for downstream processing."""
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data).decode(encoding, errors="replace")
    return str(data)


def unique_path(directory: Path, filename: str) -> Path:
    """Generate a unique file path inside directory."""
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    while True:
        candidate = directory / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def html_to_text(html: str) -> str:
    """Convert HTML to plain text for PDF rendering."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n").strip()


def save_text_pdf(text: str, out_path: Path, title: str | None = None) -> None:
    """Write multiline text into a very small PDF using ReportLab."""
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(out_path), pagesize=letter)
    story = []
    if title:
        story.append(Paragraph(title, styles["Heading4"]))
        story.append(Spacer(1, 12))
    story.append(Preformatted(text or "(no content)", styles["Code"]))
    doc.build(story)


def extract_plain_text(msg: EmailMessage) -> str:
    """Return best-effort plain text body from an EmailMessage."""
    body_part = msg.get_body(preferencelist=("plain", "html"))
    if body_part is not None:
        content = body_part.get_content()
        if body_part.get_content_type() == "text/html":
            return html_to_text(content)
        return content or ""

    if msg.get_content_type() == "text/html":
        return html_to_text(msg.get_content())

    if msg.get_content_type().startswith("text/"):
        return msg.get_content()

    # fall back to first text part without disposition
    for part in msg.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition():
            continue
        if part.get_content_type().startswith("text/"):
            content = part.get_content()
            if part.get_content_type() == "text/html":
                return html_to_text(content)
            return content or ""

    return ""


def build_email_summary(msg: EmailMessage) -> str:
    """Compose metadata + body summary for PDF output."""
    header_order = ("Subject", "From", "To", "Cc", "Bcc", "Date")
    parts = []
    for key in header_order:
        value = msg.get(key)
        if value:
            parts.append(f"{key}: {value}")
    parts.append("")
    parts.append(extract_plain_text(msg))
    return "\n".join(parts).strip()


def guess_mime_from_filename(filename: str) -> tuple[str, str]:
    """Guess MIME type from filename, defaulting to octet-stream."""
    mime, _ = mimetypes.guess_type(filename)
    if mime:
        maintype, subtype = mime.split("/", 1)
        return maintype, subtype
    return "application", "octet-stream"


@dataclass
class ConversionStats:
    """Simple conversion counters."""

    emails: int = 0
    attachments: int = 0
    errors: int = 0
    source_files: int = 0
    skipped: int = 0


class MsgToEmlConverter:
    """Convert MSG files to RFC822 EML, preferring msgconvert when available."""

    def __init__(self, log: Logger = noop_log):
        self.log = log
        self.msgconvert_path = shutil.which("msgconvert")

    def convert(self, src: Path, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if self.msgconvert_path:
            try:
                self._convert_with_msgconvert(src, dest)
                return
            except Exception as exc:  # pragma: no cover - depends on runtime availability
                self.log(
                    f"msgconvert failed for {src.name}: {exc}. "
                    "Falling back to built-in MSG parser."
                )
        self._convert_with_extract_msg(src, dest)

    def _convert_with_msgconvert(self, src: Path, dest: Path) -> None:
        result = subprocess.run(  # nosec B603
            [self.msgconvert_path, "--outfile", str(dest), str(src)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                result.stderr.strip() or f"msgconvert exited with {result.returncode}"
            )

    def _convert_with_extract_msg(self, src: Path, dest: Path) -> None:
        message = extract_msg.Message(str(src))
        email_message = EmailMessage()
        try:
            if message.date:
                if isinstance(message.date, datetime):
                    email_message["Date"] = format_datetime(message.date)
                else:
                    email_message["Date"] = str(message.date)
            if message.subject:
                email_message["Subject"] = message.subject
            for header, value in (
                ("From", message.sender),
                ("To", message.to),
                ("Cc", message.cc),
                ("Bcc", message.bcc),
            ):
                if value:
                    if isinstance(value, (list, tuple, set)):
                        value = ", ".join(str(v) for v in value if v)
                    email_message[header] = str(value)

            body = ensure_text(message.body).replace("\x00", "")
            html_body = ensure_text(message.htmlBody).replace("\x00", "")
            if body:
                email_message.set_content(body)
            if html_body:
                if not body:
                    email_message.set_content(html_to_text(html_body))
                email_message.add_alternative(html_body, subtype="html")
            if not body and not html_body:
                email_message.set_content("")

            for attachment in message.attachments or []:
                data = ensure_binary_data(getattr(attachment, "data", None))
                if data is None:
                    continue
                filename = sanitize_filename(
                    getattr(attachment, "longFilename", None)
                    or getattr(attachment, "shortFilename", None)
                )
                maintype, subtype = guess_mime_from_filename(filename)
                if not data:
                    continue
                email_message.add_attachment(
                    data,
                    maintype=maintype,
                    subtype=subtype,
                    filename=filename,
                )
        finally:
            message.close()

        dest.write_bytes(email_message.as_bytes(policy=policy.SMTP))


class EmailConverter:
    """Co-ordinate MSG→EML and PDF rendering."""

    def __init__(
        self,
        input_root: Path,
        output_root: Path,
        log: Logger | None = None,
        truncate_for_windows: bool = False,
    ):
        self.input_root = input_root.resolve()
        self.output_root = output_root.resolve()
        self.eml_root = self.output_root / "eml"
        self.pdf_root = self.output_root / "pdf"
        self.log = log or noop_log
        self.msg_converter = MsgToEmlConverter(log=self.log)
        self.truncate_for_windows = bool(truncate_for_windows)
        self.filename_limit = WINDOWS_FILENAME_LIMIT if self.truncate_for_windows else DEFAULT_FILENAME_LIMIT

        if not self.input_root.exists():
            raise FileNotFoundError(f"Input directory {self.input_root} does not exist.")
        if not self.input_root.is_dir():
            raise NotADirectoryError(f"{self.input_root} is not a directory.")
        try:
            if self.output_root.is_relative_to(self.input_root):
                raise ValueError("Output directory cannot be inside input directory.")
        except AttributeError:  # pragma: no cover - Python <3.9
            pass

    def convert_all(
        self,
        progress: Callable[[int, int, Path], None] | None = None,
    ) -> ConversionStats:
        files = self._discover_files()
        total = len(files)
        stats = ConversionStats()
        stats.source_files = total
        if not files:
            self.log("No MSG/EML files found under the selected directory.")
            return stats

        for idx, src in enumerate(files, start=1):
            try:
                rel = src.relative_to(self.input_root)
                if not rel.name or not Path(rel.name).stem:
                    raise ValueError(
                        f"Email file '{rel.name or src.name}' is missing characters before the extension."
                    )
                rel = self._prepare_relative(rel)
                eml_path = self._ensure_eml(src, rel)
                attachment_count = self._render_pdf(eml_path, rel)
                stats.emails += 1
                stats.attachments += attachment_count
                self.log(f"Converted: {src.relative_to(self.input_root).as_posix()}")
            except Exception as exc:
                stats.errors += 1
                if DEBUG:
                    import traceback

                    traceback.print_exc()
                self.log(f"ERROR processing {src.name}: {exc}")
            finally:
                if progress:
                    progress(idx, total, src)

        stats.skipped = max(0, stats.source_files - stats.emails - stats.errors)
        return stats

    def _discover_files(self) -> list[Path]:
        return sorted(
            p
            for p in self.input_root.rglob("*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES
        )

    def _prepare_relative(self, rel: Path) -> Path:
        if not self.truncate_for_windows:
            return rel
        new_name = self._truncate_component(rel.name)
        if new_name != rel.name:
            self.log(f"Truncated long filename for Windows compatibility: {rel.name} → {new_name}")
        return rel.with_name(new_name)

    def _truncate_component(self, name: str) -> str:
        if not self.truncate_for_windows:
            return name
        limit = self.filename_limit
        if limit <= 0 or len(name) <= limit:
            return name
        stem, ext = os.path.splitext(name)
        keep = max(1, limit - len(ext))
        return stem[:keep] + ext

    def _ensure_eml(self, src: Path, rel: Path) -> Path:
        if src.suffix.lower() == ".eml":
            dest = self.eml_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            return dest
        dest = self.eml_root / rel.with_suffix(".eml")
        self.msg_converter.convert(src, dest)
        return dest

    def _render_pdf(self, eml_path: Path, relative_to_input: Path) -> int:
        pdf_rel = relative_to_input.with_suffix(".pdf")
        pdf_path = self.pdf_root / pdf_rel
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        with eml_path.open("rb") as handle:
            email_message = BytesParser(policy=policy.default).parse(handle)
        summary = build_email_summary(email_message)
        save_text_pdf(summary, pdf_path, title=email_message.get("Subject"))
        return self._export_attachments(email_message, pdf_path)

    def _export_attachments(self, msg: EmailMessage, email_pdf_path: Path) -> int:
        attachments = list(msg.iter_attachments())
        if not attachments:
            return 0
        attachments_dir_name = f"{email_pdf_path.stem}_attachments"
        attachments_dir_name = self._truncate_component(attachments_dir_name)
        attachments_dir = email_pdf_path.parent / attachments_dir_name
        count = 0
        for part in attachments:
            filename = sanitize_filename(part.get_filename(), max_length=self.filename_limit)
            payload = attachment_payload_bytes(part)
            content_type = part.get_content_type()
            pdf_filename = self._truncate_component(Path(filename).stem + ".pdf")
            pdf_dest = unique_path(attachments_dir, pdf_filename)
            try:
                convert_attachment_payload(filename, payload, content_type, pdf_dest)
            except Exception as exc:
                self.log(f"Attachment {filename} failed: {exc}")
                save_text_pdf(
                    f'Attachment "{filename}" could not be converted.\nError: {exc}',
                    pdf_dest,
                )
            count += 1
        return count


def convert_attachment_payload(
    filename: str,
    payload: bytes,
    content_type: str,
    dest_pdf: Path,
) -> None:
    """Convert attachment payload bytes into a PDF file."""
    if not payload:
        save_text_pdf(f"Attachment {filename} was empty.", dest_pdf)
        return

    ext = Path(filename).suffix.lower()
    if ext == PDF_EXT:
        dest_pdf.write_bytes(payload)
        return

    if ext in IMAGE_ATTACHMENT_EXTS:
        if Image is None:
            raise RuntimeError("Pillow is required to convert image attachments.")
        with Image.open(BytesIO(payload)) as img:
            img.convert("RGB").save(dest_pdf, format="PDF")
        return

    if ext in TEXT_ATTACHMENT_EXTS:
        text = payload.decode("utf-8", errors="replace")
        save_text_pdf(text, dest_pdf, title=f"Attachment: {filename}")
        return

    if ext in HTML_ATTACHMENT_EXTS:
        text = html_to_text(payload.decode("utf-8", errors="ignore"))
        save_text_pdf(text, dest_pdf, title=f"Attachment: {filename}")
        return

    if content_type == "message/rfc822":
        inner = BytesParser(policy=policy.default).parsebytes(payload)
        summary = build_email_summary(inner)
        save_text_pdf(summary, dest_pdf, title=f"Attached email: {filename}")
        return

    save_text_pdf(
        textwrap.dedent(
            f"""
            Attachment {filename} ({content_type or 'unknown type'}) could not be
            converted automatically. Please open the original attachment from the
            source MSG/EML or convert it manually.
            """
        ).strip(),
        dest_pdf,
    )


def attachment_payload_bytes(part) -> bytes:
    """
    Normalize an attachment's payload to bytes.

    Some attachments (especially those coming from msgconvert output) may return
    str objects even when decode=True is passed. This helper keeps downstream
    conversion code happy by forcing everything to bytes.
    """
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        charset = part.get_content_charset() or "utf-8"
        return payload.encode(charset, errors="replace")

    raw = part.get_payload()
    if isinstance(raw, bytes):
        return raw
    if isinstance(raw, str):
        charset = part.get_content_charset() or "utf-8"
        return raw.encode(charset, errors="replace")
    return b""


def run_cli(args: argparse.Namespace) -> None:
    """Execute conversions from the command line."""
    input_root = Path(args.input).expanduser().resolve()
    output_root = Path(args.output).expanduser().resolve()

    log_file_handle = None
    if args.log_file:
        log_file_handle = Path(args.log_file).expanduser().open("a", encoding="utf-8")

    def _log(message: str) -> None:
        print(message)
        if log_file_handle:
            log_file_handle.write(message + "\n")
            log_file_handle.flush()

    try:
        converter = EmailConverter(input_root, output_root, log=_log)
        stats = converter.convert_all()
        _log(
            f"Finished: {stats.emails} emails, {stats.attachments} attachments, "
            f"{stats.errors} errors."
        )
    finally:
        if log_file_handle:
            log_file_handle.close()


class ConverterGUI:
    """Tkinter front-end for selecting folders and running conversions."""

    def __init__(self) -> None:
        if not tk:
            raise RuntimeError("Tkinter is not available in this environment.")
        self.root = tk.Tk()
        self.root.title("MSG/EML to PDF Converter")
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Idle")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.queue: queue.Queue = queue.Queue()
        self.worker: threading.Thread | None = None

        self._build_layout()
        self._poll_queue()

    def _build_layout(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(column=0, row=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        ttk.Label(frame, text="Input folder:").grid(column=0, row=0, sticky="w")
        input_entry = ttk.Entry(frame, textvariable=self.input_var, width=70)
        input_entry.grid(column=0, row=1, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="Browse…", command=self._browse_input).grid(
            column=1, row=1, sticky="ew"
        )

        ttk.Label(frame, text="Output folder:").grid(column=0, row=2, sticky="w", pady=(12, 0))
        output_entry = ttk.Entry(frame, textvariable=self.output_var, width=70)
        output_entry.grid(column=0, row=3, sticky="ew", padx=(0, 8))
        ttk.Button(frame, text="Browse…", command=self._browse_output).grid(
            column=1, row=3, sticky="ew"
        )

        frame.columnconfigure(0, weight=1)

        ttk.Button(frame, text="Start Conversion", command=self._start_conversion).grid(
            column=0, row=4, columnspan=2, pady=(16, 8), sticky="ew"
        )

        ttk.Label(frame, textvariable=self.status_var).grid(
            column=0, row=5, columnspan=2, sticky="w"
        )

        progress = ttk.Progressbar(
            frame,
            maximum=100.0,
            variable=self.progress_var,
            mode="determinate",
        )
        progress.grid(column=0, row=6, columnspan=2, sticky="ew", pady=(8, 12))

        log_frame = ttk.Frame(frame)
        log_frame.grid(column=0, row=7, columnspan=2, sticky="nsew")
        frame.rowconfigure(7, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=18, wrap="word", state="disabled")
        self.log_text.grid(column=0, row=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log_text.yview,
        )
        scrollbar.grid(column=1, row=0, sticky="ns")
        self.log_text["yscrollcommand"] = scrollbar.set

    def _browse_input(self) -> None:
        path = filedialog.askdirectory(title="Select source folder")
        if path:
            self.input_var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Select destination folder")
        if path:
            self.output_var.set(path)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _queue_log(self, message: str) -> None:
        self.queue.put(("log", message))

    def _start_conversion(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Conversion running", "Please wait, conversion in progress.")
            return

        input_path = Path(self.input_var.get()).expanduser()
        output_path = Path(self.output_var.get()).expanduser()
        if not input_path.is_dir():
            messagebox.showerror("Invalid input", "Please select a valid input directory.")
            return
        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Output error", f"Could not create output directory: {exc}")
                return

        self.progress_var.set(0.0)
        self.status_var.set("Preparing…")

        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        def worker() -> None:
            try:
                converter = EmailConverter(input_path, output_path, log=self._queue_log)
                stats = converter.convert_all(
                    progress=lambda idx, total, src: self.queue.put(
                        (
                            "progress",
                            idx,
                            total,
                            str(Path(src).relative_to(input_path)),
                        )
                    )
                )
                self.queue.put(("done", stats))
            except Exception as exc:  # pragma: no cover - GUI worker
                self.queue.put(("fatal", str(exc)))

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._append_log(item[1])
                elif kind == "progress":
                    _, idx, total, rel_path = item
                    percent = (idx / total) * 100 if total else 0.0
                    self.progress_var.set(percent)
                    self.status_var.set(f"Processing ({idx}/{total}): {rel_path}")
                elif kind == "done":
                    stats: ConversionStats = item[1]
                    self.progress_var.set(100.0)
                    self.status_var.set(
                        f"Finished: {stats.emails} emails, {stats.attachments} attachments, "
                        f"{stats.errors} errors."
                    )
                elif kind == "fatal":  # pragma: no cover
                    messagebox.showerror("Conversion failed", item[1])
                    self.status_var.set("Failed.")
        except queue.Empty:
            pass
        finally:
            if self.root.winfo_exists():
                self.root.after(150, self._poll_queue)

    def run(self) -> None:
        self.root.mainloop()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert MSG/EML folders to flattened EML/PDF outputs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-i", "--input", help="Root folder containing MSG/EML files.")
    parser.add_argument("-o", "--output", help="Destination folder for converted files.")
    parser.add_argument(
        "--log-file",
        help="Optional log file to append CLI progress to.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Force launching the GUI.",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Disable GUI auto-launch when CLI arguments are missing.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.gui:
        if not tk:
            raise RuntimeError("Tkinter is not available. Run with --input/--output instead.")
        ConverterGUI().run()
        return

    if args.input and args.output:
        run_cli(args)
        return

    if not args.no_gui and tk:
        ConverterGUI().run()
        return

    raise SystemExit("Input and output paths are required when GUI mode is disabled.")


if __name__ == "__main__":
    main()




