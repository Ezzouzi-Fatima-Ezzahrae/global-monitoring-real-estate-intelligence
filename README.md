# Global Monitoring & Real Estate Intelligence System

A multi-agent monitoring and analysis pipeline built for Orchid Island, a
luxury real estate company in Marrakech. It watches political, economic,
regional, expert-commentary, real-estate-sector, and video news in real
time, runs every event through a structured adversarial debate, scores its
business impact with a knowledge-base-backed judge agent, and can deliver
a daily digest by WhatsApp, Telegram, and email.

This repository contains the application code. Raw scraped datasets,
generated reports, confidential company dossiers, and real credentials are
intentionally excluded (see `.gitignore`) and are not part of this repo.

## Key features

- **Five parallel monitoring agents** (political, economic, expert
  commentary, regional MENA/Morocco, real estate sector) plus a sixth
  agent that monitors YouTube video content, each running real web search
  against a curated, configurable list of outlets.
- **Two-voice adversarial debate.** Every event is reviewed by a primary
  LLM ("Defender") and a second, independently configured provider
  ("Challenger"), in a bounded, at most three-round exchange, so a review
  never shares one model's blind spots.
- **Judge agent.** Turns each event and its debate outcome into a sourced
  impact assessment (sector, direction, magnitude, confidence, time
  horizon, recommended action), drawing supporting context from a lexical
  (BM25) retrieval-augmented knowledge base.
- **Document upload and analysis**, including real OCR (PyMuPDF +
  Tesseract) for scanned PDFs with no text layer.
- **Daily notifications** over WhatsApp, Telegram, and email, each channel
  optional and independently configured.
- **A local web console** (FastAPI + plain HTML/CSS/JS, English/French/
  Arabic) showing live and past runs, PDF export, the document library,
  and per-event notes.

## No mock mode

Every required credential is checked at the point it's needed; a missing
one raises a clear, named configuration error (`src/errors.py`) rather
than running on fabricated data. A real call that fails (a rate limit, a
network blip) is reported honestly as a failed or skipped step, never
silently replaced with invented content. The automated test suite runs
fully offline, but only via dependency injection at the test boundary
(`tests/conftest.py` monkeypatches the external calls for that test run);
the running application always calls the real services or raises.

## Architecture

```
global-monitoring-real-estate-intelligence/
├── src/
│   ├── models/          # Event, DebateLog, ImpactAssessment, DailyReport, PipelineState
│   ├── tools/           # web_search, fetch_page, extract_content, pdf_extraction (+ OCR), calculator, YouTube search/transcript
│   ├── services/        # llm_client, knowledge_base (RAG), run_store, run_persistence, pdf_export,
│   │                    # document_store, chat_assistant, source_classification, translation,
│   │                    # whatsapp_notifier, telegram_notifier, email_notifier
│   ├── agents/          # monitoring_agent (6 configured instances), debate_agent, judge_agent, document_agent
│   ├── orchestrator/    # LangGraph graph: fan-out -> collect -> debate -> judge -> format_report
│   ├── api/
│   │   ├── main.py      # FastAPI app -- see "Local console" below for the route list
│   │   └── static/      # the local console: plain HTML/CSS/JS, no build step, EN/FR/AR
│   ├── config/          # settings.py -- .env loading, settings.require(...)
│   └── errors.py        # MissingConfigurationError
├── tests/               # 289 tests, all pass offline via test-level monkeypatching
├── knowledge_base/      # general market/tourism/macro reference material used by the RAG judge
├── scripts/
│   ├── demo_run.py      # runnable end-to-end demo, with an upfront config check
│   └── daily_notify.py  # standalone daily job: run pipeline, persist, attempt WhatsApp + Telegram + email, always exit 0
├── requirements.txt
├── .env.example
└── .gitignore
```

## Getting started

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in real credentials -- see that file for where to get each one

pytest                      # 289 tests, run fully offline

uvicorn src.api.main:app --reload --port 8000
# open http://localhost:8000 for the local console, or:
curl -X POST http://localhost:8000/run-digest
```

`scripts/demo_run.py` prints an upfront configuration check (which
credentials are actually set) before running anything, so a missing one is
obvious immediately rather than surfacing as a confusing failure partway
through.

## Configuration

All configuration lives in `.env` (copy `.env.example` to start). The
required credentials are:

- `LLM_API_KEY` / `LLM_PROVIDER` -- the primary model (Gemini by default;
  an Anthropic path is also wired).
- `GROQ_API_KEY` -- the independent second voice used by the debate stage.
- `WEB_SEARCH_API_KEY` -- the web search / news provider.

Optional, each independently configured and honestly skipped if left
blank:

- `YOUTUBE_API_KEY` -- for the YouTube Video Monitoring Agent.
- `OCR_ENABLED`, `TESSERACT_CMD`, `OCR_LANGUAGES`, `OCR_MAX_PAGES`,
  `OCR_DPI` -- OCR for scanned PDF uploads (see `.env.example` for install
  steps per OS).
- WhatsApp, Telegram, and email notification settings (see "Daily
  notifications" below).

See `.env.example` for the full, commented list, including where to obtain
each key.

## Local console

`uvicorn src.api.main:app --reload --port 8000`, then open
`http://localhost:8000`. One process, no separate frontend server, no
build step -- the page is served directly by the same FastAPI app.

Main routes:

- `GET /health` -- which required credentials are actually configured.
- `POST /run-digest` / `POST /run-digest-and-notify` -- run the real
  pipeline, optionally followed by a real notification attempt.
- `GET /runs`, `GET /runs/{id}`, `GET /runs/{id}/pdf` -- run history and
  PDF export.
- `POST /documents/upload`, `GET /documents`, `GET /documents/{id}`,
  `GET /documents/{id}/pdf`, `DELETE /documents/{id}` -- the document
  library (multi-file upload, folder upload, OCR for scans).
- `POST /notify/test`, `GET /notify/status` -- verify notification
  credentials without running the full pipeline.
- `POST /chat` -- the in-console assistant.
- `PUT /runs/{run_id}/events/{event_id}/note` -- per-event notes, saved
  onto that run's own record.

Every run is saved and indexed (`src/services/run_store.py`, a small
SQLite index over the run history), so past runs remain browsable, not
just the latest one.

## Daily notifications

Three independent, optional channels, each honestly reported as skipped
if its credentials are not set:

- **WhatsApp** via callmebot.com (free, personal use, one-time opt-in) or
  Twilio.
- **Telegram** via a bot created through `@BotFather`.
- **Email** via plain SMTP (works with Gmail, Office 365, or any SMTP
  relay) -- the channel that carries the full PDF report as an
  attachment.

See `.env.example` for exact setup steps for each. Once configured,
`scripts/daily_notify.py` is meant to be triggered once a day by an OS-level
scheduler (there is no built-in scheduler in the FastAPI app itself) --
on Windows, via Task Scheduler (`schtasks`); on macOS/Linux, via `cron` or
a `launchd`/`systemd` timer.

## Knowledge base

`src/services/knowledge_base.py` implements lexical (BM25 keyword)
retrieval over `knowledge_base/`, used by the judge agent to ground its
impact assessments. No embeddings or vector database are used or needed at
this corpus size. The files included here are general market, tourism, and
macroeconomic reference material; company-specific confidential records
(land parcels, specific listings, investment-opportunity dossiers) are
kept out of this public repository and are not part of the RAG corpus
shipped here.

## Adding a new monitoring source

Add one entry to `MONITORING_AGENTS` in `src/agents/monitoring_agent.py`
for a source that fits an existing `source_type` (`web` or `youtube`). A
genuinely new retrieval pipeline (a different platform's own API) means
adding a new `source_type` branch inside `run_monitoring_agent()` as well,
the same way the YouTube branch was added.

## Known limitations

- **Free-tier LLM rate limiting.** A single run can make 15-20+ model
  calls in quick succession; on a free-tier key this can hit a rate limit
  partway through. Affected items are skipped or recorded as a failed
  step with the real error, never silently filled in. A paid tier, or
  basic backoff between calls, removes this.
- **Generic source list.** The curated outlet list in
  `monitoring_agent.py` is a starting point, not a final one -- it is
  straightforward to add or remove outlets per source.
- **Distribution/dashboard phase** is not yet built.
- **Social platforms.** TikTok's Research API excludes commercial users
  and Instagram's official API only covers your own business account, so
  neither is wired in; the only alternative would be scraping, which
  risks violating those platforms' terms of service.
