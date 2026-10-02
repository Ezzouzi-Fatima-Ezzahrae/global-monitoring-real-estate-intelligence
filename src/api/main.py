"""FastAPI app — V1+Phase3 scope: a JSON API (/health, /run-digest, /runs,
/runs/{id}/pdf) plus a self-contained local GUI served at "/" from the same
process, so `uvicorn src.api.main:app` is the only thing you need to start
(see src/orchestrator/graph.py for what's implemented vs. planned in the
pipeline itself).

No mock mode anywhere in this file: /run-digest always runs the real
pipeline (real search, real LLM calls) against whatever MissingConfigurationError
-checked credentials are actually configured — see src/config/settings.py.

2026-09-11 additions: every run is now also indexed in a small SQLite
database (src/services/run_store.py) alongside the existing full JSON file
under reports/runs/ — the JSON stays the full record, SQLite is just a
queryable index over it. GET /runs/{run_id}/pdf renders that run's report
as a real, downloadable PDF (src/services/pdf_export.py).

Same-day addition: POST /run-digest-and-notify runs the real pipeline like
/run-digest, then makes a best-effort attempt to notify Orchid Island over
WhatsApp (src/services/whatsapp_notifier.py), Telegram
(src/services/telegram_notifier.py, 2026-09-21 addition), and email
(src/services/email_notifier.py). All three channels are optional — a
missing credential is reported back as an honest "skipped" reason, never a
fabricated "sent", and never fails the run itself (which already
succeeded and was saved before notification is attempted). For the
actual daily automation (not a manual API call), see
scripts/daily_notify.py and README.md "Daily automatic notifications".

2026-09-21 addition: POST /documents/upload and the GET/DELETE
/documents* routes let Orchid Island upload a PDF directly in the console
and get back real, AI-extracted events grounded in that specific file
(src/agents/document_agent.py) — kept deliberately separate from the
automated daily pipeline above (confirmed directly with Orchid Island),
so a result comes back the moment a document is uploaded rather than
waiting for or being folded into that day's report.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.agents.document_agent import analyze_uploaded_pdf
from src.config import settings
from src.errors import MissingConfigurationError
from src.orchestrator import run_pipeline
from src.services import (
    chat_assistant,
    document_store,
    email_notifier,
    pdf_export,
    run_persistence,
    run_store,
    telegram_notifier,
    translation,
    whatsapp_notifier,
)
from src.tools.pdf_extraction import PdfTextNotFoundError

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Global Monitoring & Real Estate Intelligence System", version="0.1.0")

STATIC_DIR = Path(__file__).parent / "static"
RUNS_DIR = Path(__file__).resolve().parents[2] / "reports" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)
DOCUMENTS_DIR = Path(__file__).resolve().parents[2] / "reports" / "documents"
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

# Serves the logo/favicon assets (src/api/static/*.png) at /static/* -- the
# GUI itself is still served by the index() route below reading
# index.html's text directly, not through this mount; this only exists so
# <img>/<link> tags in that page have real files to point at.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _db_path() -> Path:
    """SQLite index over reports/runs/*.json (see src/services/run_store.py).
    Computed from the *current* value of RUNS_DIR, not captured at import
    time, so a test that does monkeypatch.setattr(api_main, "RUNS_DIR", tmp_path)
    gets a fully isolated database alongside its isolated run files."""
    return RUNS_DIR / "index.db"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Serves the local GUI (src/api/static/index.html) from this same
    process — no separate frontend server, no CORS to configure. The page
    itself calls /health, /run-digest and /runs on this same origin."""
    html_path = STATIC_DIR / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=500, detail=f"GUI file missing: {html_path}")
    return html_path.read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    """Reports honestly which required credentials are actually configured —
    there is no mock mode to fall back to, so /run-digest will fail (with a
    clear MissingConfigurationError surfaced per-agent in its trace) for
    anything reported False here."""
    return {
        "status": "ok",
        "llm_api_key_configured": bool(settings.llm_api_key),
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "groq_api_key_configured": bool(settings.groq_api_key),
        "web_search_api_key_configured": bool(settings.web_search_api_key),
        "timezone": settings.timezone,
    }


@app.get("/notify/status")
def notify_status() -> dict:
    """2026-09-22 addition, for the Alerts page: which notification
    channels have real, complete credentials configured right now --
    read-only, no secret values returned. Mirrors exactly the fields each
    notifier's own settings.require() call checks (see
    whatsapp_notifier.py, telegram_notifier.py, email_notifier.py) so this
    can never drift out of sync with what a real send actually needs.
    Additive only -- does not change how /run-digest-and-notify or
    /notify/test behave."""
    if settings.whatsapp_provider == "callmebot":
        whatsapp_ok = bool(settings.callmebot_api_key and settings.whatsapp_to_numbers)
    else:
        whatsapp_ok = bool(
            settings.twilio_account_sid and settings.twilio_auth_token
            and settings.twilio_whatsapp_from and settings.whatsapp_to_numbers
        )
    telegram_ok = bool(settings.telegram_bot_token and settings.telegram_chat_ids)
    email_ok = bool(
        settings.smtp_host and settings.smtp_username and settings.smtp_password
        and settings.email_from and settings.email_to
    )
    return {
        "whatsapp": {"configured": whatsapp_ok, "provider": settings.whatsapp_provider},
        "telegram": {"configured": telegram_ok},
        "email": {"configured": email_ok},
    }


@app.post("/run-digest")
def run_digest() -> dict:
    """Triggers one real pipeline run synchronously (real search, real LLM
    calls — can genuinely take a minute or more) and returns the full
    structured result, now including Judge's per-event impact analysis
    (Phase 5, first version — see src/orchestrator/graph.py). Also persists
    it to reports/runs/<run_id>.json (and indexes it, see
    run_persistence.persist_run) so /runs can list real run history rather
    than this being throwaway. Never sends notifications — see POST
    /run-digest-and-notify."""
    try:
        state = run_pipeline()
    except Exception as exc:  # a real, unexpected failure — never hidden
        logger.exception("run_pipeline() raised unexpectedly")
        raise HTTPException(status_code=500, detail=f"Pipeline run failed: {exc}") from exc

    _run_id, run, _json_path = run_persistence.persist_run(state, RUNS_DIR)
    return run


def _attempt_notifications(run: dict) -> dict:
    """Best-effort WhatsApp + Telegram + email send for one already-
    persisted run. Each channel is independent: a missing credential is
    reported as an honest {"skipped_reason": ...} rather than raised, and
    one channel's real failure never blocks the others. Never claims a
    channel was sent when it wasn't."""
    result: dict = {"whatsapp": None, "telegram": None, "email": None}

    try:
        result["whatsapp"] = whatsapp_notifier.send_whatsapp_report(run)
    except MissingConfigurationError as exc:
        result["whatsapp"] = {"sent_to": [], "skipped_reason": str(exc)}
    except Exception as exc:
        logger.error("WhatsApp notification failed: %s", exc)
        result["whatsapp"] = {"sent_to": [], "error": str(exc)}

    try:
        result["telegram"] = telegram_notifier.send_telegram_report(run)
    except MissingConfigurationError as exc:
        result["telegram"] = {"sent_to": [], "skipped_reason": str(exc)}
    except Exception as exc:
        logger.error("Telegram notification failed: %s", exc)
        result["telegram"] = {"sent_to": [], "error": str(exc)}

    try:
        pdf_bytes = pdf_export.build_report_pdf(run)
        result["email"] = email_notifier.send_email_report(run, pdf_bytes)
    except MissingConfigurationError as exc:
        result["email"] = {"sent_to": [], "skipped_reason": str(exc)}
    except Exception as exc:
        logger.error("Email notification failed: %s", exc)
        result["email"] = {"sent_to": [], "error": str(exc)}

    return result


@app.post("/run-digest-and-notify")
def run_digest_and_notify() -> dict:
    """Same real pipeline run and persistence as POST /run-digest, plus a
    best-effort attempt to notify Orchid Island over WhatsApp and email
    (2026-09-11 addition). This is the manual/on-demand equivalent of what
    scripts/daily_notify.py does once a day when scheduled — see
    README.md "Daily automatic notifications" for the schedule."""
    try:
        state = run_pipeline()
    except Exception as exc:
        logger.exception("run_pipeline() raised unexpectedly")
        raise HTTPException(status_code=500, detail=f"Pipeline run failed: {exc}") from exc

    _run_id, run, _json_path = run_persistence.persist_run(state, RUNS_DIR)
    run["notifications"] = _attempt_notifications(run)
    return run


@app.post("/notify/test")
def notify_test() -> dict:
    """Sends a small, clearly-labeled CONNECTIVITY TEST message over
    WhatsApp and email — not a real report — so you can verify your
    Twilio/SMTP credentials are wired correctly without waiting for a full
    (real search + real LLM) pipeline run. Same honest skip/error
    reporting as POST /run-digest-and-notify."""
    test_run = {
        "run_id": "connectivity-test",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_date": datetime.now(timezone.utc).date().isoformat(),
        "trace": [],
        "events": [],
        "report": {
            "report_date": datetime.now(timezone.utc).date().isoformat(),
            "headline": "This is a connectivity test message from the Orchid Island Digest Console — not a real report.",
            "top_events": [],
            "no_significant_events": True,
            "limitations": [],
        },
    }
    return _attempt_notifications(test_run)


@app.get("/runs")
def list_runs(limit: int = 20) -> list[dict]:
    """Real run history, from the SQLite index (src/services/run_store.py)
    over reports/runs/*.json — newest first. Nothing here is seeded or
    fabricated; an empty list just means no run has happened yet. A
    one-time backfill indexes any JSON files that predate this index
    (e.g. this project's own 2026-09-10 real run) so real history is never
    silently dropped just because the index is new."""
    db_path = _db_path()
    run_store.backfill_from_json_files(RUNS_DIR, db_path)
    return run_store.list_runs(db_path, limit=limit)


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    path = RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No run found with id {run_id!r}")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


@app.get("/runs/{run_id}/pdf")
def get_run_pdf(run_id: str) -> Response:
    """Real PDF export of one run's report (2026-09-11 addition), built
    directly from the same structured DailyReport every other view uses
    (src/services/pdf_export.py) — not a markdown-to-PDF conversion. A
    missing run is still a real 404, same as GET /runs/{run_id}."""
    path = RUNS_DIR / f"{run_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No run found with id {run_id!r}")
    run = json.loads(path.read_text(encoding="utf-8"))
    pdf_bytes = pdf_export.build_report_pdf(run)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="orchid_island_digest_{run_id}.pdf"'},
    )


@app.get("/runs/{run_id}/translation/{lang}")
def get_run_translation(run_id: str, lang: str) -> dict:
    """On-demand French/Arabic translation of one run's real content
    (2026-09-22 addition, requested directly by Orchid Island — see src/
    services/translation.py's module docstring). Translated once per
    run+lang and cached onto the run's own JSON file; every call after the
    first is a cache read, not a new LLM call. A missing run is a real 404,
    same as every other /runs/{run_id}* route; a missing LLM credential is
    a real 503, same as every other AI-backed route in this file."""
    if lang not in translation.SUPPORTED_LANGS:
        raise HTTPException(status_code=400, detail=f"Unsupported language {lang!r}; supported: fr, ar")
    try:
        return run_persistence.get_or_create_translation(run_id, lang, RUNS_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissingConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # a real, unexpected translation failure -- never hidden, never cached
        logger.exception("Run translation failed for run_id=%s lang=%s", run_id, lang)
        raise HTTPException(status_code=500, detail=f"Translation failed: {exc}") from exc


class EventNoteRequest(BaseModel):
    text: str


class ChatTurn(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    message: str
    run_id: str | None = None
    history: list[ChatTurn] = []
    lang: str = "en"  # 2026-09-22: console's current language, so the assistant answers in it too


@app.post("/chat")
def chat(body: ChatRequest) -> dict:
    """Real, grounded question-and-answer over whichever run is currently
    loaded in the console (if any) plus the Phase 4 knowledge base (2026-
    09-16 addition — see src/services/chat_assistant.py). Replaces the
    earlier per-event "notes & questions" boxes, which only let you leave a
    note, never get an answer back. A missing LLM credential is a real,
    honest error here too — never a fabricated response."""
    run = None
    if body.run_id:
        run_path = RUNS_DIR / f"{body.run_id}.json"
        if run_path.exists():
            run = json.loads(run_path.read_text(encoding="utf-8"))

    try:
        result = chat_assistant.answer_question(
            run=run,
            question=body.message,
            history=[turn.model_dump() for turn in body.history],
            lang=body.lang,
        )
    except MissingConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # a real, unexpected failure -- never hidden
        logger.exception("chat_assistant.answer_question() raised unexpectedly")
        raise HTTPException(status_code=500, detail=f"Chat failed: {exc}") from exc
    return result


@app.put("/runs/{run_id}/events/{event_id}/note")
def set_event_note(run_id: str, event_id: str, body: EventNoteRequest) -> dict:
    """A place to leave a note or question against one event in a past run
    (2026-09-14 addition, requested directly by Orchid Island: "a place to
    ask questions") — GET /runs/{run_id} already returns whatever is saved
    here (see run_persistence.save_event_note), since notes live on the
    same run JSON file. Blank text clears the note rather than storing an
    empty one. A run or event id that does not exist is a real 404, same
    honesty standard as every other endpoint here — this never silently
    writes a note against a made-up id."""
    try:
        note = run_persistence.save_event_note(run_id, event_id, body.text, RUNS_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"run_id": run_id, "event_id": event_id, "note": note}


# ---------------------------------------------------------------------------
# Uploaded documents (2026-09-21 addition) — see module docstring and
# src/agents/document_agent.py. Deliberately its own small section, not
# threaded through run_persistence.py/RUNS_DIR: an uploaded document is not
# a pipeline run, and its own storage (src/services/document_store.py)
# reflects that.
# ---------------------------------------------------------------------------


@app.post("/documents/upload")
async def upload_document(request: Request, file: UploadFile = File(...)) -> dict:
    """Real PDF upload + AI extraction: reads the real uploaded file,
    extracts its real text (src/tools/pdf_extraction.py), and asks the LLM
    to find every real, grounded event in it that could affect Moroccan
    real estate (src/agents/document_agent.py). Every extracted event's
    source_url is this same document's own GET /documents/{id}/pdf URL —
    built from the real incoming request's base URL, so it resolves
    correctly whether the app is reached as localhost or a LAN address.

    A file with no usable text (e.g. a scanned image with no text layer)
    is a real, honest 422 with the specific reason — not a fabricated
    empty success — and is still saved so it shows up in the console with
    that reason rather than silently vanishing."""
    filename = file.filename or "uploaded.pdf"
    is_pdf_name = filename.lower().endswith(".pdf")
    if file.content_type not in ("application/pdf", "application/x-pdf", "application/octet-stream") and not is_pdf_name:
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    max_bytes = settings.document_upload_max_bytes
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File is too large ({len(file_bytes) / 1_048_576:.1f} MB): "
                f"the limit is {max_bytes / 1_048_576:.0f} MB."
            ),
        )

    document_id = document_store.new_document_id()
    source_url = f"{request.base_url}documents/{document_id}/pdf"

    try:
        result = analyze_uploaded_pdf(file_bytes, filename=filename, source_url=source_url, document_id=document_id)
    except PdfTextNotFoundError as exc:
        document_store.save_document(
            document_id,
            filename=filename,
            file_bytes=file_bytes,
            events=[],
            page_count=0,
            limitations=[],
            error=str(exc),
            documents_dir=DOCUMENTS_DIR,
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MissingConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # a real, unexpected failure -- never hidden
        logger.exception("document_agent.analyze_uploaded_pdf() raised unexpectedly")
        raise HTTPException(status_code=500, detail=f"Document analysis failed: {exc}") from exc

    return document_store.save_document(
        document_id,
        filename=filename,
        file_bytes=file_bytes,
        events=result["events"],
        page_count=result["page_count"],
        limitations=result["limitations"],
        documents_dir=DOCUMENTS_DIR,
    )


@app.get("/documents")
def list_documents() -> list[dict]:
    """Every uploaded document, newest first — summaries only (filename,
    when, page/event counts, and the real error if one failed); GET
    /documents/{document_id} below has the full extracted event list for
    one document. An empty list just means nothing has been uploaded yet."""
    return document_store.list_documents(DOCUMENTS_DIR)


@app.get("/documents/{document_id}")
def get_document(document_id: str) -> dict:
    record = document_store.get_document(document_id, DOCUMENTS_DIR)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No document found with id {document_id!r}")
    return record


@app.get("/documents/{document_id}/pdf")
def get_document_pdf(document_id: str) -> Response:
    """Serves back the real, original uploaded PDF — this is the same URL
    every event extracted from it cites as its source_url, so a claim can
    always be checked against the actual file."""
    path = document_store.get_document_pdf_path(document_id, DOCUMENTS_DIR)
    if path is None:
        raise HTTPException(status_code=404, detail=f"No document found with id {document_id!r}")
    return Response(
        content=path.read_bytes(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{path.name}"'},
    )


@app.get("/documents/{document_id}/translation/{lang}")
def get_document_translation(document_id: str, lang: str) -> dict:
    """On-demand French/Arabic translation of one uploaded document's
    extracted events — same on-demand-and-cache pattern as GET
    /runs/{run_id}/translation/{lang} above (see src/services/
    translation.py)."""
    if lang not in translation.SUPPORTED_LANGS:
        raise HTTPException(status_code=400, detail=f"Unsupported language {lang!r}; supported: fr, ar")
    try:
        return document_store.get_or_create_translation(document_id, lang, DOCUMENTS_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MissingConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # a real, unexpected translation failure -- never hidden, never cached
        logger.exception("Document translation failed for document_id=%s lang=%s", document_id, lang)
        raise HTTPException(status_code=500, detail=f"Translation failed: {exc}") from exc


@app.delete("/documents/{document_id}")
def delete_document(document_id: str) -> dict:
    """Removes an uploaded document and its extraction results — e.g. the
    wrong file was uploaded. A document id that doesn't exist is a real
    404, same honesty standard as every other endpoint here."""
    found = document_store.delete_document(document_id, DOCUMENTS_DIR)
    if not found:
        raise HTTPException(status_code=404, detail=f"No document found with id {document_id!r}")
    return {"deleted": document_id}
