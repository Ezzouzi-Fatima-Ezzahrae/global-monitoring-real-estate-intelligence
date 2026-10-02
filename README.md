# Global Monitoring & Real Estate Intelligence System

> **Status: V1 in progress.** Phases 0–3 (repo skeleton, schemas, tools, the
> 5 independent monitoring agents, the orchestrator, and a real two-voice
> adversarial debate stage) are implemented and tested below, running
> against real LLMs (Gemini + Groq) and real live web search — see "Real
> LLM, always real" and "Structured debate, not just a single model."
> Phase 5 (Judge — turning each event + its debate outcome into a real,
> sourced impact assessment) is now implemented too, in a first version:
> see "What's built vs. what's next" for its honest scope limit. Phase 4
> (RAG knowledge base) is now **implemented** (2026-09-15) — real, lexical
> (BM25 keyword) retrieval over `knowledge_base/`, including a first real
> batch of Orchid Island company data (real land titles, a real Orchid
> Island listing, real investment-opportunity dossiers) cleaned from
> scanned documents, plus 119,770 real scraped Marrakech listings
> aggregated into comparable-pricing data — see `knowledge_base/README.md`
> for exactly what is in it and what is still missing. **This system has no
> mock/fallback mode** — see "No mock mode: what
> that actually means" below. All three required credentials (`LLM_API_KEY`,
> `GROQ_API_KEY`, `WEB_SEARCH_API_KEY`) are now configured and verified
> end-to-end — see the real-run notes there for the one genuine limitation
> that run surfaced (Gemini free-tier rate limiting under this pipeline's
> current call volume).

This is the working implementation of the system described in the
**Concept & Architecture Report**, the **Cahier des Charges**, and the
**Execution Plan** delivered alongside this repo. Read those first for the
full design; this README covers what actually runs today.

## No mock mode: what that actually means

This system does not fabricate data, sources, or model output anywhere. Every
required credential (`LLM_API_KEY`, `GROQ_API_KEY`, `WEB_SEARCH_API_KEY`) is
checked at the point it's needed via `settings.require(...)`
(`src/config/settings.py`); if it's missing, the code raises
`MissingConfigurationError` (`src/errors.py`) immediately, naming exactly
which `.env` variable to set — it never silently substitutes a fixture or a
keyword heuristic instead. If a real API call fails, that failure propagates
honestly (see `src/orchestrator/graph.py`'s per-node trace, which records a
failed step with the real error message) rather than being papered over.

The one place this system *does* return an empty result instead of raising
is a genuine, transient per-call failure after credentials are confirmed
present — e.g. `web_search()` catching a network blip and logging it rather
than crashing the whole daily run (FR-14: one source outage shouldn't take
down the other four agents). That's an honest "this one call failed right
now," never a fabricated stand-in for what the call would have returned.

**This is separate from how the automated test suite works.** `pytest`
still runs fully offline with zero external accounts and zero network
calls — but it does this the standard way any Python test suite avoids
hitting a real, paid API: `tests/conftest.py` and the individual test files
use `pytest`'s `monkeypatch` to inject deterministic fakes at the seams
(`web_search`, `fetch_page`, `llm_client.summarize_event`,
`llm_client.complete_json`, or the `httpx` calls underneath them) for that
one test run, then pytest reverts them. This is dependency injection at the
test level, not a code path the shipped product can ever fall into — the
running system always calls the real thing or raises
`MissingConfigurationError`. `tests/conftest.py`'s module docstring spells
this distinction out for anyone reading the test code.

**Practical consequence:** as of this delivery, `LLM_API_KEY`, `GROQ_API_KEY`
and `WEB_SEARCH_API_KEY` are all configured, and `scripts/demo_run.py` has
been run end-to-end against real Tavily search results and real Gemini
summaries — the full pipeline (all 5 monitoring agents → debate →
report) genuinely runs today, not just in theory.

That real run also surfaced two honest, real limitations worth flagging
rather than quietly working around:

- **Gemini free-tier rate limiting.** A single run makes up to ~15–20
  Gemini calls in quick succession (per-article summaries across 5 agents,
  plus the debate stage). On the free tier this hit `429 Too Many Requests`
  partway through — the affected articles were skipped (or, for the debate
  stage, the whole step recorded as `failed` with the real error) exactly
  as designed: an honest gap in the report, never a fabricated fill-in. A
  paid Gemini tier, or spacing out the calls, would remove this; tell me if
  you'd like me to add basic rate-limiting/backoff between agents so a
  free-tier key doesn't need to hit this at all.
- **Page-extraction quality on some sources.** `extract_content()` is a
  simple HTML→text strip (see its docstring in
  `src/tools/content_extraction.py`); on a few real pages that returned
  site navigation or a category-listing page rather than a specific
  article, the model correctly summarized *that* (there's nothing else to
  work with) rather than inventing article content — again honest, but it
  means some events in a real run are less substantive until the source
  list (item 4 below) narrows queries to specific outlets/articles rather
  than general topic searches.

Neither of these is mock/fake data — both are the system behaving exactly
as designed when a real call hits a real, ordinary limitation. The daily
Cowork scheduled task remains a separate, independent path to a live
digest (it performs its own search rather than going through this repo's
pipeline).

## Real data, not mock

`knowledge_base/` and `reports/2026-09-09_real_digest_example.md` contain
**genuine, sourced content collected via live web search on 2026-09-09** —
real Bank Al-Maghrib figures, real 2026 tourism statistics, a real COVID-era
precedent for how Moroccan real estate responded to a past shock, and a
hand-assembled real-data example of the daily report format. Every claim in
those files links to its actual source (see the sourcing note upgrade in
`knowledge_base/macro_morocco.md` — institutional/trade sources such as
Bank Al-Maghrib's own release, Knight Frank, and W Hospitality Group,
alongside the original outlets, rather than relying on a single
investment-marketing site). This is part of the real material Phase 4 (RAG,
now implemented — see `src/services/knowledge_base.py` and
`knowledge_base/README.md`) retrieves from, alongside a newer batch of
real Orchid Island company data and Marrakech market comparables added
2026-09-15 — it has no code dependency beyond that and is unrelated to how
the test suite stays offline (see above).

## Real source targeting (new)

The 2026-09-10 real run (see `reports/2026-09-10_automated_pipeline_run.md`)
surfaced generic topic searches sometimes landing on a homepage or
category-listing page instead of one article — an honest result (the model
correctly said "this is a navigation menu"), just not a useful one. Fixed
two ways, both verified directly against the real Tavily API before being
wired into the agents:

- **`include_domains`** — each of the 5 `MONITORING_AGENTS` in
  `src/agents/monitoring_agent.py` now restricts search to a curated list
  of real, named, currently-operating outlets (Reuters/AP/Al Jazeera/BBC
  for political, Reuters/Bloomberg/IMF/World Bank for economic,
  Project Syndicate/VoxEU/Brookings for written expert commentary —
  written analysis extracts far better than a podcast's own page, which is
  usually just an episode list — Hespress/Morocco World News/Médias24/The
  Arab Weekly for MENA/Morocco, and Knight Frank/JLL/CBRE/Hotel News Now
  for real estate). This is a **starting list I chose**, not a final one —
  see "What I need from you" item 4: tell me any subscriptions you already
  hold, or outlets to add or drop.
- **`recency_days`** — for the three fast-moving, wire-service-style
  categories (political, economic, expert commentary), search is further
  restricted to the last 7 days via Tavily's news mode, verified to return
  same-week dated articles instead of years-old ones. Verified the same way
  that this does *not* help the other two categories (MENA/Morocco, real
  estate) — their relevant content isn't well covered by Tavily's news
  index, so those two stay on plain relevance-ranked search, which found
  better real results in direct testing.

This real testing also caught a real bug: Tavily's news-mode results return
`published_date` as an RFC 2822 string (`"Fri, 04 Sep 2026 20:34:06 GMT"`),
which `Event`'s date field couldn't parse — silently dropping every real
event from the three news-mode agents (caught by the per-article
try/except and logged, not fabricated, but a real event was there and got
lost). Fixed by `_parse_published_date()` in `monitoring_agent.py`, which
handles both real formats (ISO from `extract_content()`'s own detection,
RFC 2822 from Tavily) and falls back to `None` rather than crashing the
event over a date string quirk. `tests/test_agents.py` has a regression
test for this — a real bug found on a real run, not a hypothetical one.

## Real LLM, always real

`LLM_PROVIDER=gemini` + a real `LLM_API_KEY` in `.env` makes
`src/services/llm_client.py` call the actual **Gemini API**
(`gemini-3.6-flash`, via `httpx` directly against the REST endpoint — no
extra SDK). Verified with a real key: `scripts/demo_run.py` ran against
live search results and got genuine model-written summaries and
interpretations back. A provider-agnostic Anthropic path is also wired
(`LLM_PROVIDER=anthropic`) if you'd rather use Claude — uncomment
`anthropic` in `requirements.txt` if you switch.

**Important:** `.env` is git-ignored and was **not** included in the
delivered zip — the keys used to verify this lived only in the sandbox
that built it. Anyone running this project needs to put their own keys in
`.env` (copy `.env.example`; every value is required, none has a fallback).

## Structured debate, not just a single model (Phase 3)

`src/agents/debate_agent.py` runs a bounded, ≤3-round adversarial review of
each day's events, using **two independently-configured LLM voices** so the
review doesn't share one model's blind spots:

- **Defender** — the primary LLM (`LLM_PROVIDER`/`LLM_API_KEY`, Gemini by
  default), representing the monitoring agents' own findings.
- **Challenger** — `GROQ_API_KEY`, a *different provider* (Groq, hosting
  `openai/gpt-oss-120b` behind an OpenAI-compatible REST API), whose only
  job is to look for reasons an event might be overstated, under-sourced,
  or open to another reading.

Round 1: Challenger reviews every event and flags specific objections (none
found → resolved immediately). Round 2: Defender responds to each
objection — concede (resolved, revised) or defend. Round 3 (final, bounded):
Challenger makes the last call — resolved, contested, or uncertain; nothing
is ever silently dropped (FR-06). Both `LLM_API_KEY` and `GROQ_API_KEY` are
required for this stage — `run_debate()` raises `MissingConfigurationError`
naming whichever is missing rather than running a one-voice review.
Verified end-to-end with real keys via `scripts/demo_run.py`; because a
clean day's news resolved in round 1 without exercising rounds 2–3 live,
`tests/test_debate_agent_real_mode_logic.py` separately verifies those
branches (concession, contested final call, a provider returning nothing
usable, and a provider outage propagating honestly) via test-level
monkeypatching of `llm_client.complete_json` — see "No mock mode" above for
why that's not the same thing as a product mock mode.

## What's built vs. what's next

| Layer | Status |
|---|---|
| Pydantic schemas (Event, DebateLog, ImpactAssessment, DailyReport, PipelineState) | ✅ Implemented, tested |
| Tools (web_search, fetch_page, extract_content, calculator) | ✅ Implemented, tested — always real, no fallback; `WEB_SEARCH_API_KEY` still needed (see below) |
| LLM client abstraction | ✅ Implemented and **verified against real Gemini + Groq keys** — always real, no fallback; Anthropic path also wired |
| 6 monitoring agents (Political, Economic, Expert Commentary, Regional MENA/Morocco, Real Estate Sector, YouTube Video) | ✅ Implemented, tested — run independently, in parallel. **2026-09-16 addition:** YouTube Video Monitoring Agent (real search + real transcript summarization) — needs a real `YOUTUBE_API_KEY` to retrieve anything real; not yet live-verified against the real API (see "What I need from you" item 9) |
| LangGraph orchestrator (fan-out → collect → debate → judge → format_report) | ✅ Implemented, tested |
| FastAPI app (`/health`, `/run-digest`, `/run-digest-and-notify`, `/notify/test`, `/runs`, `/runs/{id}`, `/runs/{id}/pdf`) | ✅ Implemented, tested |
| Run-history database (SQLite index over reports/runs/*.json) | ✅ Implemented, tested (new, 2026-09-11) — see "Run history database" above |
| PDF export of a run's report | ✅ Implemented, tested (new, 2026-09-11) — see "Local GUI" above |
| Daily WhatsApp + email notifications (`src/services/whatsapp_notifier.py`, `email_notifier.py`, `scripts/daily_notify.py`) | ✅ Implemented, tested (new, 2026-09-11; WhatsApp now also supports callmebot as a free alternative to Twilio, 2026-09-14) — both channels optional, honestly skipped if not configured; see "Daily automatic notifications" below. **Needs your callmebot (or Twilio) + SMTP credentials to actually send** (see item 8 below) |
| Structured ≤3-round debate (Phase 3) | ✅ Implemented, tested, verified against real Gemini+Groq keys — two-voice adversarial review, see above |
| Judge synthesis / impact assessment (Phase 5, first version) | ✅ Implemented, tested (new, 2026-09-14; now draws on Phase 4 RAG, 2026-09-15) — turns each event + its debate outcome into a structured, sourced impact assessment (sector, direction, magnitude, confidence, time horizon, recommended action), shown per-event in the Digest Console GUI and in the PDF export. Also retrieves from Orchid Island's own company data and the curated knowledge base below when it actually matches an event, and records exactly which knowledge-base sections it used in `supporting_evidence` |
| RAG knowledge base (Phase 4) | ✅ Implemented (2026-09-15) — real, lexical (BM25 keyword) retrieval over `knowledge_base/`, no embeddings/vector DB (none needed at this corpus size, and no embedding endpoint is configured anywhere in this project). Judge (above) retrieves from it per event. Corpus now includes a first real batch of Orchid Island company data and Marrakech market comparables (see `knowledge_base/README.md`) — still growing, and confirmation of current deal status on a few of the company files is still needed from you (see "What I need from you" below) |
| Distribution & dashboard (Phase 6) | ❌ Not implemented |
| Live web search (real `/run-digest` output) | ✅ Configured and verified — `/run-digest` and `scripts/demo_run.py` now run end-to-end on real Tavily search results. See "Real LLM, always real" above for the two real limitations that run surfaced (Gemini free-tier rate limiting; extraction quality on generic-topic pages) |

This matches the Execution Plan's sequencing: Phase 2 was the right place to
stop and check in, because Phases 3–5 need real decisions from you, not more
code. Phase 3 didn't need those decisions (it only needed a second LLM
key), so it's built. Phase 4 (RAG) is now built too, on real company data
found in your project folder (`Orchid data/`) rather than waiting on the
priority-markets decision — see "What I need from you" below for what
would still sharpen it (confirmed deal status on a few files, priority
markets/asset classes to focus the next batch of comparable data on).

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in real keys — every value is required, there is no fallback

python scripts/demo_run.py  # checks what's configured, then runs the pipeline and prints the report

pytest                      # 98 tests, all pass offline via test-level monkeypatching (see "No mock mode" above)

uvicorn src.api.main:app --reload --port 8000
# then open http://localhost:8000 in your browser for the local GUI (see below),
# or: curl -X POST http://localhost:8000/run-digest
```

`scripts/demo_run.py` prints an upfront configuration check (which of
`LLM_API_KEY` / `GROQ_API_KEY` / `WEB_SEARCH_API_KEY` are set) before
running anything, so a missing credential is obvious immediately rather
than surfacing as a confusing failure partway through.

## Local GUI (new)

`uvicorn src.api.main:app --reload --port 8000`, then open
**http://localhost:8000** in your browser. That's the whole setup — one
process, no separate frontend server, no build step, nothing hosted
outside your machine. The page (`src/api/static/index.html`) is served
directly by the same FastAPI app and talks to it over plain fetch calls
to `/health`, `/run-digest`, and `/runs`.

What it does, all against the real API, never mock data:

- On load, shows which of the 3 required credentials are actually
  configured (green/red badges from a real `GET /health` call) — if
  something's missing, it tells you plainly rather than letting a click
  fail mysteriously later.
- **Run digest** calls `POST /run-digest`, which runs the real pipeline —
  real Tavily search, real Gemini summaries, real Groq-vs-Gemini debate —
  and can genuinely take a minute or more; the page says so rather than
  looking frozen. The real agent trace (including any real per-agent
  failure, shown with its actual error text) and the real report render as
  they come back.
- Every run is saved to `reports/runs/<run_id>.json` — a **View run**
  dropdown lets you come back to any past real run, not just the latest
  one. Nothing here is seeded: the dropdown starts empty until you run the
  pipeline for the first time.
- Per-event debate status (resolved / contested / uncertain) is shown as a
  badge pulled directly from the real `debate_log`, not inferred.
- Each event with a Judge assessment (Phase 5) shows the real
  sector/direction/magnitude/confidence pills **plus a plain-language
  "Why" rationale** (2026-09-14 addition) — the model's actual reasoning
  for that call, not just the verdict numbers, and its recommended action
  labeled separately underneath.
- **Notes & questions** (2026-09-14 addition) — every event has its own
  small text box to leave a note or a question while reading a report.
  Saved via `PUT /runs/{run_id}/events/{event_id}/note` straight onto that
  run's JSON file, so it's still there next time you open that run — not
  generated or touched by any agent, purely your own annotation.
- **Download PDF** (2026-09-11 addition) — next to the report header, a
  real PDF of whatever run is currently shown downloads via
  `GET /runs/{run_id}/pdf` (see `src/services/pdf_export.py`), built from
  the same structured report fields the page itself renders, not a
  screenshot or a markdown conversion.
- **Also notify (WhatsApp + email)** (2026-09-11 addition) — a checkbox
  next to Run digest. Checked, "Run digest" calls
  `POST /run-digest-and-notify` instead of `POST /run-digest`: same real
  pipeline run, plus a real attempt to notify over WhatsApp and email. Each
  channel's actual result (sent / honestly skipped / real error) renders as
  a pill next to the button — never a fabricated "sent". **Test
  notifications** calls `POST /notify/test` to send a small,
  clearly-labeled connectivity-test message over both channels without
  running the (real search + real LLM, potentially slow) pipeline — use it
  to check your callmebot (or Twilio) / SMTP credentials are wired
  correctly. See "Daily
  automatic notifications" below for full setup and the actual daily
  schedule (this GUI button is the manual/on-demand equivalent of that).

This is a plain local web page, not a Claude Artifact — it couldn't be one
even if I wanted it to, since Artifacts can't reach `localhost`, and this
needs to call your real backend with your real keys. Nothing about your
`.env` or your API keys ever leaves your machine.

## Run history database (new)

Every real `/run-digest` call still writes its full result to
`reports/runs/<run_id>.json` — that JSON file remains the complete,
human-readable record of a run, and nothing below replaces it.

As of 2026-09-11 that history is *also* indexed in a small SQLite database
at `reports/runs/index.db` (`src/services/run_store.py`), so `GET /runs`
answers from a real, queryable index instead of re-reading and re-parsing
every JSON file on every request. It's deliberately minimal: one table, no
ORM, stdlib `sqlite3` only — zero new dependency. If `reports/runs/*.json`
files already exist the first time this runs (true for the two real runs
already in this project), they're automatically backfilled into the index
rather than silently dropped.

One real, concrete thing this fixed along the way, worth knowing about if
you ever see it again: SQLite's default write mode failed with a
"disk I/O error" the first time this was tested against your actual
connected project folder — that folder is reached through a virtualized/
synced mount (this bridge, and very plausibly Windows' OneDrive Desktop
backup too, if your Desktop is OneDrive-synced), which doesn't reliably
support the file-locking SQLite normally uses. `run_store.py` now opens
the database with `journal_mode=MEMORY` and `synchronous=OFF`, verified to
fix it — a safe trade-off specifically because this database is a
derived, rebuildable index, not the source of truth.

Not a general-purpose database, and not the RAG vector store either — that
remains separate, not-yet-built infrastructure (see "What's built vs.
what's next" and item 5 below).

## Daily automatic notifications (WhatsApp + Email)

At your request ("send a WhatsApp message for the report and an email to
the company to notify them each day"), the system can now notify Orchid
Island automatically, once a day, over both channels — but it never
fabricates a send: with no credentials configured, every call below still
runs the real pipeline and saves the real report, and simply reports each
channel as honestly skipped, naming exactly which `.env` variable is
missing.

**Why callmebot + plain SMTP, specifically:**

- **WhatsApp → callmebot.com's free WhatsApp API** (2026-09-14, switched
  from Twilio at your request after Twilio's cost beyond the free Sandbox
  didn't work for you — `src/services/whatsapp_notifier.py`), called
  directly over REST. No monthly cost, no Meta Business verification, but
  it's personal use only and each recipient has to opt in once:

  1. Open <https://www.callmebot.com/blog/free-api-whatsapp-messages/> and
     find the current bot number — this changes from time to time, which
     is exactly why it isn't printed here or hardcoded in the code.
  2. Add that number as a WhatsApp contact and send it, exactly:
     `I allow callmebot to send me messages`
  3. Within a couple of minutes it replies with your API key. Put that in
     `CALLMEBOT_API_KEY`, and your own number in `WHATSAPP_TO_NUMBERS`
     (with country code, e.g. `+212600000000`).

  Twilio is still supported (`WHATSAPP_PROVIDER=twilio`) if you'd rather
  pay for that instead — see `.env.example`. Whichever provider,
  **the same real constraint applies, stated honestly, not worked
  around:** neither can attach a file to a WhatsApp message without a
  public URL, and this system runs entirely on your machine with nothing
  hosted publicly. So the WhatsApp message is a concise **text** digest
  (headline + top events, flagged by relevance); the full PDF report goes
  out over **email** instead, which handles real attachments natively.
- **Email → plain SMTP** (`src/services/email_notifier.py`, stdlib
  `smtplib` — zero new dependency). Works with any provider: Gmail (use an
  app password), Office 365, a company mail server, or a transactional
  service's SMTP relay. This is the channel that carries the real PDF
  attachment (`src/services/pdf_export.py`).

**Setup — add to your `.env`** (see `.env.example` for the full commented
list): `WHATSAPP_PROVIDER` (`callmebot` or `twilio`), `CALLMEBOT_API_KEY`
(or the `TWILIO_*` fields if you use Twilio instead), `WHATSAPP_TO_NUMBERS`
for WhatsApp; `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`,
`EMAIL_FROM`, `EMAIL_TO` for email. Both channels are independent — you can
configure just one, both, or neither. **Restart the server after editing
`.env`** — settings are only read once, at startup, so a running server
keeps using its old values until you stop and start it again.

**Verify your credentials before trusting the daily schedule** — this
sends a small, clearly-labeled "CONNECTIVITY TEST... not a real report"
message over both channels, without running the (real search + real LLM,
can take a minute+) pipeline:

```bash
curl -X POST http://localhost:8000/notify/test
```

or click **Test notifications** in the local GUI.

**Manual/on-demand real run + notify**, the same real pipeline as
`POST /run-digest` plus a best-effort send over both channels:

```bash
curl -X POST http://localhost:8000/run-digest-and-notify
```

or check **Also notify (WhatsApp + email)** before clicking **Run digest**
in the GUI.

**The actual daily automation** is `scripts/daily_notify.py` — a
standalone script (run pipeline → persist → attempt WhatsApp → attempt
email → always exit 0, since a notification failure must never look like
the pipeline itself failed) meant to be triggered once a day by an
OS-level scheduler. This project's FastAPI server has no built-in
scheduler of its own — it's a local process you start, not an always-on
host — so the OS is what actually triggers it once a day. On your Windows
machine, register it with Task Scheduler (`schtasks`) — adjust the paths
to your actual project location and Python install, and pick whatever
time you want the daily run to fire (07:00 below):

```bat
schtasks /Create /SC DAILY /ST 07:00 /TN "OrchidIslandDailyDigest" ^
  /TR "\"C:\Users\Fatima ezzahrae\Desktop\global-monitoring-real-estate-intelligence\.venv\Scripts\python.exe\" \"C:\Users\Fatima ezzahrae\Desktop\global-monitoring-real-estate-intelligence\scripts\daily_notify.py\"" ^
  /RU "%USERNAME%"
```

(Run once from an elevated Command Prompt or PowerShell window. Confirm it
registered with `schtasks /Query /TN "OrchidIslandDailyDigest"`, and test
it immediately without waiting a day via
`schtasks /Run /TN "OrchidIslandDailyDigest"`. To remove it later:
`schtasks /Delete /TN "OrchidIslandDailyDigest" /F`.) If your project
folder or Python path differ from the example above (e.g. you're not
using a `.venv`), adjust both quoted paths accordingly — a plain
`python.exe` or `py.exe` from `where python` works too.

Every run this triggers is saved and indexed exactly like a manual
`POST /run-digest` — it shows up in the local GUI's **View run** dropdown
and in `GET /runs`, same as any other run.

## Project structure

```
global-monitoring-real-estate-intelligence/
├── src/
│   ├── models/        # Event, DebateLog, ImpactAssessment, DailyReport, PipelineState
│   ├── tools/          # web_search, fetch_page, extract_content, calculator
│   ├── services/
│   │   ├── llm_client.py  # real calls only — Gemini/Groq/Anthropic
│   │   ├── run_store.py   # SQLite run-history index (new) — reports/runs/index.db
│   │   ├── pdf_export.py  # renders a run's report as a real PDF (new)
│   │   ├── run_persistence.py  # shared JSON-write + SQLite-index logic (new) — used by main.py and daily_notify.py
│   │   ├── whatsapp_notifier.py  # real WhatsApp send, callmebot or Twilio (new) — optional, honest skip if unconfigured
│   │   └── email_notifier.py     # real SMTP send with PDF attached (new) — optional, honest skip if unconfigured
│   ├── agents/         # generalized monitoring_agent + 5 configured instances, debate_agent (Phase 3)
│   ├── orchestrator/    # LangGraph graph (Phase 1-3 scope)
│   ├── api/
│   │   ├── main.py       # FastAPI app: /health, /run-digest, /run-digest-and-notify, /notify/test, /runs, /runs/{id}, /runs/{id}/pdf, and "/" (serves the GUI)
│   │   └── static/index.html  # the local GUI — plain HTML/CSS/JS, no build step
│   ├── config/          # settings (.env loading, settings.require(...))
│   └── errors.py         # MissingConfigurationError
├── tests/               # 98 tests, all pass offline via test-level monkeypatching
├── reports/
│   ├── runs/             # JSON history (source of truth) + index.db (derived index, new)
│   └── *.md               # hand-assembled/example real-data reports
├── scripts/
│   ├── demo_run.py        # runnable end-to-end demo, with an upfront config check
│   └── daily_notify.py    # standalone daily job (new) — run pipeline, persist, attempt WhatsApp + email, always exit 0
├── requirements.txt
├── .env.example
└── .gitignore
```

## Adding a 7th monitoring source

**2026-09-16 update:** the 6th source (YouTube) has been added — see
`MonitoringAgentConfig.source_type` in `src/agents/monitoring_agent.py`
(`"web"` or `"youtube"`) and the `YouTube Video Monitoring Agent` entry in
`MONITORING_AGENTS`. Adding a 7th still works the way this section always
described, for a source that fits one of the existing two retrieval
pipelines:

Add one entry to `MONITORING_AGENTS` in `src/agents/monitoring_agent.py` —
that's it for a source using an existing `source_type` (`web` or
`youtube`). A genuinely new retrieval pipeline (e.g. a different
platform's own API) means adding a new `source_type` branch inside
`run_monitoring_agent()` too, the same way the YouTube branch was added —
but no fixtures to update, no other file changes beyond that: this is the
config-driven extensibility the Cahier des Charges requires (NFR:
maintainability).

## What I need from you to keep going

The code above is real and tested. As of this delivery it runs fully
end-to-end against real LLMs (Gemini + Groq) and real live web search — the
three credential blockers are all resolved. The rest are genuine blockers
for Phase 4 onward, not busywork:

1. ~~An LLM API key~~ — **done.** A Gemini key is configured and verified
   end-to-end via `scripts/demo_run.py`. `LLM_PROVIDER=anthropic` is also
   wired if you'd rather use Claude instead — just say so.
2. ~~A second LLM for the debate stage~~ — **done.** A Groq key is
   configured as the independent "Challenger" voice (see "Structured
   debate" above), verified end-to-end.
3. ~~A web search / news API key~~ — **done.** A Tavily key is configured
   and verified end-to-end — `/run-digest` and `scripts/demo_run.py` now
   produce real results from real search. One thing worth a decision from
   you: that real run hit Gemini's free-tier rate limit partway through
   (see "Real LLM, always real" above) — tell me if you'd like basic
   rate-limiting/backoff added so a free-tier key handles this pipeline's
   call volume cleanly, or if a paid tier is the simpler fix on your end.
4. **The final source list** — ~~partially done.~~ I've curated and wired
   in a starting list myself (see "Real source targeting" above) —
   Reuters/AP/Al Jazeera/BBC/Foreign Policy, Bloomberg/IMF/World Bank,
   Project Syndicate/VoxEU/Brookings, Hespress/Morocco World
   News/Médias24/The Arab Weekly, and Knight Frank/JLL/CBRE/Hotel News Now,
   verified to return real, specific, fetchable articles rather than
   homepages. **2026-09-11 addition** (per your request for broader
   international coverage, since a war/conflict abroad can reach prices
   here): the Global Political News Agent now also covers CNN, The
   Guardian, The New York Times, Deutsche Welle, France 24, The Economist,
   Middle East Eye, and the Financial Times; the Global Economic & Markets
   Agent now also covers the U.S. Energy Information Administration
   (eia.gov) and S&P Global (spglobal.com) for the oil/energy-cost channel
   specifically, since Morocco is a net energy importer (see
   `knowledge_base/macro_morocco.md`). Honest caveat: unlike the original
   list, these additions could not be re-verified against the live Tavily
   API from the session that added them (outbound access to
   `api.tavily.com` was blocked by that session's own sandboxed network) —
   run one real `POST /run-digest` to confirm they behave the way the
   original list was verified to. Still open: tell me any subscriptions you
   already hold (a trade publication, a paid research feed) so I match the
   real integration to it, and flag anything you'd rather I not cite.
5. ~~Confirmation of 2–3 priority markets/asset classes~~ — **partially
   overtaken by events.** Rather than wait, I built Phase 4 (RAG) on the
   real company data already sitting in your `Orchid data/` project folder
   (see `knowledge_base/README.md`) — Marrakech villas, especially
   Palmeraie/Amelkis, ended up as the deepest comparable-data coverage
   simply because that folder already had a dedicated luxury-villa dataset
   for that area. If a different market/asset class matters more, tell me
   and I'll prioritize the next batch of comparable data there instead.
6. ~~Company data access~~ — **first real batch done, 2026-09-15**, cleaned
   from scanned documents in `Orchid data/data-orchide-scanné/`: a real
   Orchid Island listing, two real land title records, and dossiers for
   two investment opportunities under evaluation. Each of those files ends
   with its own open questions — the main one across all of them is
   **confirming current deal/ownership status** (is Tingis Plaza, Atlas
   Golf Marrakech, or either Route de Casablanca parcel a live matter, a
   closed one, or just a market comparable being tracked?), since I could
   only go by what the documents themselves say, not what happened since
   they were scanned.
7. **A decision on the Phase 7 human reviewer** — who will actually read
   and give feedback on generated reports once distribution (Phase 6) is
   built; not needed yet, but worth deciding early per the Execution Plan.
8. **callmebot (or Twilio) + SMTP credentials, to actually send the daily
   WhatsApp + email notifications** (2026-09-11 addition, per your
   request; WhatsApp provider switched to callmebot 2026-09-14 as a free
   alternative to Twilio) — the code, tests, GUI controls, and
   daily-schedule script are all built and working; without a real
   `CALLMEBOT_API_KEY` (or the `TWILIO_*` fields if `WHATSAPP_PROVIDER` is
   set back to `twilio`), `WHATSAPP_TO_NUMBERS`, and `SMTP_HOST` /
   `SMTP_USERNAME` / `SMTP_PASSWORD` / `EMAIL_FROM` / `EMAIL_TO` values in
   your `.env`, both channels report themselves as honestly skipped rather
   than sending anything. See "Daily automatic notifications" above for
   exactly what to get and where from (the free callmebot opt-in; any
   SMTP-capable mailbox).
9. **A YOUTUBE_API_KEY, to actually run the new YouTube Video Monitoring
   Agent** (2026-09-16 addition, per your request to also monitor video
   content) — free, official Google API, no billing account needed at
   this usage level; see `.env.example` for exactly how to get one. The
   agent, its two tools (real YouTube search + real transcript retrieval),
   and their tests are all built, but none of it has been verified against
   the real API yet — no key was available in the session that built it.
   Also worth a decision from you: TikTok's own Research API explicitly
   excludes commercial users, and Instagram's official API only covers
   your own business account rather than monitoring others', so neither is
   wired in — the only way to cover them would be scraping, which risks
   violating those platforms' terms of service, so it wasn't built. Tell me
   if you'd like to revisit that, or if X/Twitter (paid, pay-per-call, no
   free tier as of this year) is worth the added recurring cost.

With #1–3 done, the full V1+Phase3+Phase4+Phase5 pipeline runs end-to-end
on real data today, Judge included. #4 also happens to be the fix for the
extraction-quality issue above; #5–6 are about deepening/confirming the RAG
corpus, not unblocking it, since a first real version is already built and
wired in. #8 and #9 are the same story for the two notification/YouTube
features: the code, tests, and (for #9) real-API design are done, and a
real credential is what's standing between each one and actually doing
something today.
