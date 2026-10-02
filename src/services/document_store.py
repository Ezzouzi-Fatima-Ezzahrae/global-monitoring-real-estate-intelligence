"""Persistence for uploaded-document analyses (2026-09-21 addition).

Mirrors src/services/run_persistence.py's shape (one JSON record per item,
newest-first for the list view) but deliberately simpler: no SQLite index
like src/services/run_store.py adds for runs. run_store.py's own docstring
explains why runs eventually needed one (a growing daily history that's
expensive to re-scan on every GET /runs); document uploads are expected to
stay small enough in volume that a plain directory scan is fine, and it
keeps this feature easy to reason about. Can grow a real index later the
same way runs did, if upload volume ever justifies it.

The original uploaded PDF is saved alongside its analysis JSON so GET
/documents/{document_id}/pdf can serve it back — that URL is what
src/agents/document_agent.py uses as every extracted event's real
source_url, so a citation is always literally the file it came from, the
same "prove it wasn't fabricated" guarantee FR-12 gives every other event
in this system.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.services import translation

DOCUMENTS_DIR_DEFAULT = Path(__file__).resolve().parents[2] / "reports" / "documents"


def new_document_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]


def save_document(
    document_id: str,
    *,
    filename: str,
    file_bytes: bytes,
    events: list,
    page_count: int,
    limitations: list[str],
    error: Optional[str] = None,
    documents_dir: Path = DOCUMENTS_DIR_DEFAULT,
) -> dict:
    """Writes the original PDF and its analysis JSON record. `events` may
    be real pydantic Event objects or already-plain dicts — either way
    they're dumped to JSON-safe dicts here. `error` is set instead of a
    real event list when extraction genuinely failed (e.g.
    PdfTextNotFoundError) — the upload is still saved and listed with its
    real reason, rather than disappearing as if nothing happened."""
    documents_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = documents_dir / f"{document_id}.pdf"
    pdf_path.write_bytes(file_bytes)

    record = {
        "document_id": document_id,
        "filename": filename,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "page_count": page_count,
        "event_count": len(events),
        "events": [e.model_dump(mode="json") if hasattr(e, "model_dump") else e for e in events],
        "limitations": limitations,
        "error": error,
    }
    json_path = documents_dir / f"{document_id}.json"
    json_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def list_documents(documents_dir: Path = DOCUMENTS_DIR_DEFAULT) -> list[dict]:
    """Newest-first summaries (not full event lists — see get_document for
    that) for the console's document list view. An empty list just means
    nothing has been uploaded yet, same honesty guarantee GET /runs gives
    for an empty run history."""
    if not documents_dir.exists():
        return []
    records = []
    for f in documents_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        records.append(
            {
                "document_id": data.get("document_id", f.stem),
                "filename": data.get("filename", f.stem),
                "uploaded_at": data.get("uploaded_at", ""),
                "page_count": data.get("page_count", 0),
                "event_count": data.get("event_count", 0),
                "error": data.get("error"),
            }
        )
    records.sort(key=lambda r: r["uploaded_at"], reverse=True)
    return records


def get_document(document_id: str, documents_dir: Path = DOCUMENTS_DIR_DEFAULT) -> Optional[dict]:
    json_path = documents_dir / f"{document_id}.json"
    if not json_path.exists():
        return None
    return json.loads(json_path.read_text(encoding="utf-8"))


def get_document_pdf_path(document_id: str, documents_dir: Path = DOCUMENTS_DIR_DEFAULT) -> Optional[Path]:
    pdf_path = documents_dir / f"{document_id}.pdf"
    return pdf_path if pdf_path.exists() else None


def delete_document(document_id: str, documents_dir: Path = DOCUMENTS_DIR_DEFAULT) -> bool:
    """Removes both files for one document. Returns False (not an error)
    if it was already gone — deleting something twice is not a real
    failure, same as src/services/run_persistence.py treating a blank note
    as "clear it" rather than an error."""
    found = False
    for suffix in (".json", ".pdf"):
        path = documents_dir / f"{document_id}{suffix}"
        if path.exists():
            path.unlink()
            found = True
    return found


def get_or_create_translation(document_id: str, lang: str, documents_dir: Path = DOCUMENTS_DIR_DEFAULT) -> dict:
    """Same on-demand-translate-and-cache pattern as src/services/
    run_persistence.py's get_or_create_translation, scoped to one uploaded
    document's extracted events (src/services/translation.py's
    translate_document_events). Raises FileNotFoundError for an unknown
    document_id; a real translation failure propagates uncached."""
    json_path = documents_dir / f"{document_id}.json"
    if not json_path.exists():
        raise FileNotFoundError(f"No document found with id {document_id!r}")

    record = json.loads(json_path.read_text(encoding="utf-8"))
    translations = record.setdefault("translations", {})
    if lang in translations:
        return translations[lang]

    translated = translation.translate_document_events(record.get("events") or [], lang)
    translations[lang] = translated
    json_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return translated
