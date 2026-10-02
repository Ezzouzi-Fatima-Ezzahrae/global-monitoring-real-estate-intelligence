"""Centralized settings. All other modules import config from here rather
than reading os.environ directly (see docs: src/config/README.md pattern
carried over from the fact-checking project).

There is no mock mode. Every field below that names a required credential
must be set in .env for the corresponding part of the system to run — if
it's missing, the code that needs it raises `MissingConfigurationError`
(src/errors.py) immediately, naming exactly which variable is missing,
rather than silently substituting fake data. See `require()` below.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.errors import MissingConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM (primary — used by the 6 monitoring agents, and as the "defender"
    # voice in the debate stage). REQUIRED.
    llm_api_key: str = ""
    llm_provider: str = "gemini"  # "gemini" (REST, no SDK) or "anthropic" (SDK)
    llm_model: str = "gemini-3.6-flash"

    # Debate "challenger" voice (Phase 3) — deliberately a different provider
    # from llm_api_key above, so the adversarial review doesn't share the
    # primary model's blind spots. Groq hosts open-weight models (e.g.
    # OpenAI's gpt-oss) behind an OpenAI-compatible REST API. REQUIRED for
    # the debate stage specifically.
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"

    # Web search / news. REQUIRED for the 5 text-based monitoring agents to
    # retrieve anything real.
    web_search_api_key: str = ""

    # YouTube (2026-09-16 addition) — REQUIRED for the YouTube Video
    # Monitoring Agent specifically (src/agents/monitoring_agent.py); the
    # other 5 agents don't touch this key at all. Free, official Google
    # API, no billing account needed at this usage level. Get one at
    # console.cloud.google.com: create/select a project -> enable "YouTube
    # Data API v3" under APIs & Services -> Credentials -> Create API key.
    # See src/tools/youtube_search.py for what it's used for and
    # src/tools/youtube_transcript.py (a separate, keyless library) for how
    # a video's actual transcript is retrieved.
    youtube_api_key: str = ""

    # Rate / cost control
    max_search_calls_per_agent: int = 5
    max_page_fetches_per_agent: int = 8
    request_timeout_seconds: int = 10

    # 2026-09-22 addition: a document upload (src/agents/document_agent.py)
    # sends up to 12,000 characters of real extracted PDF text to the model
    # in one call -- three times request_timeout_seconds's own 4,000-char
    # article clip -- and asks for more tokens back, so it routinely needs
    # longer than the fast, per-article timeout above before it can be
    # honestly called a real failure. Kept as its own setting rather than
    # raising request_timeout_seconds globally, so the fast agents (news
    # summarization, debate, Judge, chat) still fail fast and honestly when
    # something is genuinely stuck.
    document_analysis_timeout_seconds: int = 45

    # 2026-09-24 fix: a real production upload was failing with no record
    # ever saved (POST /documents/upload raising before it could call
    # document_store.save_document) -- traced to src/services/llm_client.py's
    # Gemini call hardcoding maxOutputTokens=1500 for every call, including
    # this one. That is enough for summarize_event's single-article summary,
    # but a document can describe several distinct events, and Phase 1
    # (2026-09-24) added a "page" and an optional "section" to every one of
    # them, on top of headline/summary/sentiment/relevance/confidence/
    # agent_interpretation/supporting_quote -- a real multi-event document's
    # response routinely needs more room than that. When Gemini's own
    # completion is cut off at the token cap, the response is truncated
    # mid-JSON and fails to parse, which reaches POST /documents/upload as an
    # unexpected exception (not PdfTextNotFoundError or
    # MissingConfigurationError), so nothing is persisted and the upload
    # simply "fails" with no obvious cause. Kept as its own setting, the same
    # way document_analysis_timeout_seconds is, rather than raising every
    # call's token cap: a single-article summary never needed that much room
    # and a needlessly high cap on every call would raise real cost.
    document_analysis_max_output_tokens: int = 4000

    # 2026-09-25 fix: a real upload was rejected outright with "File is too
    # large (98,610,757 bytes) -- the limit is 26,214,400 bytes" -- that
    # 25 MB figure was a hardcoded constant in src/api/main.py
    # (_MAX_UPLOAD_BYTES), sized only for "a real report/brochure/
    # cahier-des-charges PDF" and never meant to cover a real ~94 MB
    # document. Text extraction itself (src/tools/pdf_extraction.py) reads
    # whatever pypdf can open regardless of file size and separately caps
    # the extracted text it returns (_MAX_EXTRACTED_CHARS), so raising this
    # does not send more to the LLM or change its cost -- it only decides
    # how large a raw upload this synchronous endpoint accepts before
    # saving and reading it. Moved here (from a fixed module constant) so
    # it can be raised further via .env, the same as the two settings
    # above, without editing code. 200 MB comfortably covers a real
    # multi-hundred-page or image-heavy PDF while still keeping one upload
    # request from holding the server open indefinitely.
    document_upload_max_bytes: int = 200 * 1024 * 1024

    # 2026-09-25 addition, at Orchid Island's request: a real upload turned
    # out to be a genuine scan with no text layer, which this system
    # honestly reported ("this system does not do OCR") but could not
    # analyze. src/tools/pdf_extraction.py now runs real OCR (PyMuPDF to
    # render a scanned page to an image, pytesseract/Tesseract to read it)
    # on any real page whose pypdf text is too short to be real -- never on
    # a normal, already-real-text PDF. On by default because the honest gap
    # was real and this is the real fix; set to false to go back to the
    # original "does not do OCR" behavior (e.g. if Tesseract can't be
    # installed on this machine).
    ocr_enabled: bool = True

    # Full path to the real Tesseract OCR binary. Blank (default) lets
    # pytesseract find it on PATH, which Tesseract's own installer usually
    # sets up. Set this explicitly if it wasn't added to PATH -- Windows'
    # default install location is typically
    # "C:\Program Files\Tesseract-OCR\tesseract.exe". See .env.example for
    # where to download it.
    tesseract_cmd: str = ""

    # Real Tesseract language pack(s) to read scanned pages with, "+"-
    # joined (e.g. "eng+fra+ara"). Defaults to English-only because that is
    # the one pack Tesseract's installer always includes -- OCR on a French
    # or Arabic scanned page with only "eng" loaded will misread it rather
    # than fail outright, so this needs raising the moment the French/
    # Arabic language packs are installed too (see .env.example).
    ocr_languages: str = "eng"

    # How many of a document's real scanned pages get OCR'd, at most, in
    # one upload. OCR is slow -- Tesseract reading a real image-heavy
    # multi-hundred-page scan page by page can take minutes, and
    # POST /documents/upload is still a synchronous request the browser
    # waits on. This bounds how long one upload can run; pages beyond the
    # cap are left as-is and reported as a real, honest limitation (the
    # same pattern extracted-text truncation already uses) rather than
    # silently dropped. Raise it if a machine is fast enough to wait
    # longer for a bigger scan.
    ocr_max_pages: int = 50

    # Rendering resolution (DPI) used to turn each scanned page into an
    # image before OCR. Higher improves accuracy on small or dense text at
    # the cost of a slower render and OCR pass per page; 200 is a
    # reasonable default for a typical printed document.
    ocr_dpi: int = 200

    # Daily notifications (2026-09-11 addition, optional) -- WhatsApp via
    # Twilio's WhatsApp API (a REST call, same "no extra SDK" pattern as
    # Gemini/Groq below) and email via plain SMTP (works with Gmail,
    # Office365, or any provider -- no vendor lock-in). Both are entirely
    # optional: nothing else in this system requires them, and /run-digest
    # works exactly the same with or without them configured. Only the
    # notify-specific endpoints/script (POST /run-digest-and-notify,
    # scripts/daily_notify.py) use these, and each channel is skipped with
    # a clear, honest reason if its credentials are missing -- never a
    # silent no-op and never a fabricated "sent" result.
    # "twilio" or "callmebot" -- see src/services/whatsapp_notifier.py for
    # why callmebot exists (Twilio's paid-beyond-sandbox pricing didn't work
    # for Orchid Island; callmebot is free for personal use, no monthly
    # cost, no Meta Business verification).
    whatsapp_provider: str = "twilio"
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""  # e.g. "whatsapp:+14155238886" (Twilio sandbox number)
    callmebot_api_key: str = ""  # from callmebot.com's one-time WhatsApp opt-in (see README)
    # comma-separated recipient number(s). Twilio wants "whatsapp:+212600000000";
    # callmebot wants the same number without the "whatsapp:" prefix -- either
    # form works for callmebot, whatsapp_notifier.py strips the prefix if present.
    whatsapp_to_numbers: str = ""

    # Telegram (2026-09-21 addition, optional) -- see
    # src/services/telegram_notifier.py for why this needs only one
    # provider (unlike WhatsApp's twilio/callmebot choice): Telegram's own
    # Bot API is free with no business verification. TELEGRAM_BOT_TOKEN
    # comes from @BotFather (README.md "Daily automatic notifications" has
    # the exact steps); TELEGRAM_CHAT_IDS is comma-separated, one id per
    # person/group that should receive the daily digest -- each recipient
    # must message the bot once first (Telegram won't let a bot message
    # someone who hasn't started a conversation with it), also covered in
    # the README.
    telegram_bot_token: str = ""
    telegram_chat_ids: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    # Display name recipients see instead of the raw address (e.g. an inbox
    # shows "Orchid Island - Intelligence Monitoring" rather than the bare
    # Gmail address). Optional -- blank falls back to the address alone.
    email_from_name: str = "Orchid Island - Intelligence Monitoring"
    email_to: str = ""  # comma-separated, e.g. "team@orchidisland.immo,manager@orchidisland.immo"

    # App
    api_port: int = 8000
    log_level: str = "INFO"
    timezone: str = "Africa/Casablanca"

    def require(self, field_name: str, env_var: str) -> str:
        """Fetch a required credential or raise a clear, actionable error.
        This is the one place that turns "something is missing" into an
        immediate, loud failure instead of a silent fallback — call it at
        the point a credential is actually needed, not just at startup, so
        a missing GROQ_API_KEY doesn't block the monitoring agents from
        running with only LLM_API_KEY set, for example."""
        value = getattr(self, field_name)
        if not value:
            raise MissingConfigurationError(
                f"{env_var} is not set. This system does not have a mock/fallback "
                f"mode — set {env_var} in .env (see .env.example) before running "
                "this part of the pipeline."
            )
        return value


settings = Settings()
