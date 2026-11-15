"""Load an invoice file and get its machine-readable text layer (if any)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from famcheck.ingest.normalize import detect_language

SUPPORTED = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

MAX_BYTES = 25 * 1024 * 1024


class UnsupportedFile(ValueError):
    pass


@dataclass
class SourceDoc:
    path: Path
    name: str
    data: bytes
    media_type: str
    sha256: str
    kind: str  # pdf-text | pdf-scanned | image
    text: str  # text layer used to verify evidence ("" for images / scans)
    language: str


def load(path: str | Path, display_name: str | None = None) -> SourceDoc:
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED:
        raise UnsupportedFile(f"{p.name}: unsupported type {ext} (use PDF, PNG, JPG or WEBP)")
    data = p.read_bytes()
    if len(data) > MAX_BYTES:
        raise UnsupportedFile(f"{p.name}: larger than 25 MB")
    sha = hashlib.sha256(data).hexdigest()
    text = ""
    kind = "image"
    if ext == ".pdf":
        reader = PdfReader(p)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        kind = "pdf-text" if len(text.strip()) >= 20 else "pdf-scanned"
        if kind == "pdf-scanned":
            text = ""
    return SourceDoc(
        path=p,
        name=display_name or p.name,
        data=data,
        media_type=SUPPORTED[ext],
        sha256=sha,
        kind=kind,
        text=text,
        language=detect_language(text) if text else "unknown",
    )
