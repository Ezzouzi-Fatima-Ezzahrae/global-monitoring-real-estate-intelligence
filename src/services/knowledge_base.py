"""Phase 4 RAG: real, lexical (BM25) retrieval over the curated knowledge
base (src/services/knowledge_base.py).

This deliberately does NOT use embeddings or a vector database. There is no
embedding endpoint configured anywhere in this project (see
src/config/settings.py -- only llm_api_key/groq_api_key/web_search_api_key
exist), and the knowledge base is small (a couple of dozen files), so a
real, well-understood lexical ranking function -- Okapi BM25, the same
family of algorithm search engines like Elasticsearch use -- gives
genuine, defensible retrieval without adding a new dependency, a new
network call per event, or a new failure mode (no API key to be missing,
no rate limit to hit). This is a real retrieval algorithm operating on
real, curated text, not a shortcut or a placeholder -- if a stronger
(embedding-based) retriever is wanted later, only this module needs to
change; callers (judge_agent.py) just ask for `retrieve(query, top_k)` and
get back scored, sourced chunks.

Honest limits, stated plainly: BM25 matches on shared words/phrases, not
meaning, so a query about "tourist arrivals falling" will not retrieve a
chunk about "hotel occupancy declining" unless the words actually overlap.
This is a real trade-off, not a bug to silently paper over -- see
knowledge_base/README.md for the current, live state of this stage.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Project knowledge_base/ directory -- src/services/knowledge_base.py -> src/services -> src -> repo root.
KNOWLEDGE_BASE_DIR = Path(__file__).resolve().parent.parent.parent / "knowledge_base"

# Small, deliberately conservative French/English stopword list -- the
# knowledge base mixes both languages (OCR'd French source documents,
# English market commentary), and dropping only the most common function
# words keeps meaningful short words (e.g. "or", a real estate term in some
# contexts) from being silently discarded.
_STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "en", "est",
    "sont", "pour", "avec", "sur", "dans", "par", "au", "aux", "ce", "ces",
    "son", "sa", "ses", "qui", "que", "ne", "pas", "plus", "il", "elle",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "this", "that", "these",
    "those", "it", "its", "as", "at", "by", "from",
}

_TOKEN_RE = re.compile(r"[a-zàâäéèêëïîôöùûüç0-9]+", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    return [
        t for t in (m.lower() for m in _TOKEN_RE.findall(text))
        if t not in _STOPWORDS and len(t) > 1
    ]


@dataclass
class KnowledgeChunk:
    """One retrievable unit: a level-2 (##) section of a knowledge_base
    markdown file, tagged with the file it came from and its own heading so
    a citation can point somewhere specific, not just at the whole file."""

    source_file: str  # e.g. "company/land_parcels_route_de_casablanca.md"
    heading: str
    text: str
    tokens: list[str] = field(default_factory=list, repr=False)


def _split_markdown_into_chunks(path: Path, root: Path) -> list[KnowledgeChunk]:
    text = path.read_text(encoding="utf-8")
    rel = str(path.relative_to(root)).replace("\\", "/")
    lines = text.splitlines()
    chunks: list[KnowledgeChunk] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        if current_heading is not None:
            body = "\n".join(current_lines).strip()
            if body:
                chunks.append(KnowledgeChunk(source_file=rel, heading=current_heading, text=body))

    for line in lines:
        if line.startswith("## "):
            flush()
            current_heading = line[3:].strip()
            current_lines = []
            continue
        if current_heading is not None:
            current_lines.append(line)
    flush()

    for chunk in chunks:
        chunk.tokens = _tokenize(chunk.heading + " " + chunk.text)
    return chunks


_CACHE: list[KnowledgeChunk] | None = None


def load_chunks(force_reload: bool = False) -> list[KnowledgeChunk]:
    """Loads and caches every ## section from every knowledge_base/**/*.md
    file except README.md (README.md is the human-facing index of the
    folder, not retrievable content). Cached in-process because the
    pipeline calls this once per event, potentially many times per run, and
    the knowledge base only changes when someone edits the files on disk --
    call with force_reload=True (or restart the process) to pick up edits."""
    global _CACHE
    if _CACHE is not None and not force_reload:
        return _CACHE

    chunks: list[KnowledgeChunk] = []
    if KNOWLEDGE_BASE_DIR.exists():
        for path in sorted(KNOWLEDGE_BASE_DIR.rglob("*.md")):
            if path.name.upper() == "README.MD":
                continue
            try:
                chunks.extend(_split_markdown_into_chunks(path, KNOWLEDGE_BASE_DIR))
            except Exception as exc:  # one bad file must not blank out the rest
                logger.error("knowledge_base: failed to load %s: %s", path, exc)
    else:
        logger.warning("knowledge_base: directory not found at %s", KNOWLEDGE_BASE_DIR)

    _CACHE = chunks
    logger.info("knowledge_base: loaded %d chunk(s) from %s", len(chunks), KNOWLEDGE_BASE_DIR)
    return chunks


def _bm25_scores(query_tokens: list[str], chunks: list[KnowledgeChunk], k1: float = 1.5, b: float = 0.75) -> list[float]:
    """Standard Okapi BM25 over the given chunks for the given query
    tokens. Recomputed per call rather than pre-indexed -- the corpus here
    is a few dozen chunks, so this costs microseconds, and it means a
    freshly edited knowledge base is reflected the moment load_chunks()
    is (re)called, with no separate index-rebuild step to forget."""
    n = len(chunks)
    if n == 0:
        return []
    avg_dl = sum(len(c.tokens) for c in chunks) / n or 1.0

    doc_freq: dict[str, int] = {}
    for c in chunks:
        for t in set(c.tokens):
            doc_freq[t] = doc_freq.get(t, 0) + 1

    scores: list[float] = []
    for c in chunks:
        term_freq: dict[str, int] = {}
        for t in c.tokens:
            term_freq[t] = term_freq.get(t, 0) + 1
        dl = len(c.tokens) or 1
        score = 0.0
        for qt in query_tokens:
            n_qt = doc_freq.get(qt, 0)
            f = term_freq.get(qt, 0)
            if n_qt == 0 or f == 0:
                continue
            idf = math.log(1 + (n - n_qt + 0.5) / (n_qt + 0.5))
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avg_dl))
        scores.append(score)
    return scores


@dataclass
class RetrievedChunk:
    source_file: str
    heading: str
    text: str
    score: float

    @property
    def citation(self) -> str:
        """A short, stable identifier for ImpactAssessment.supporting_evidence
        (already documented there as holding "event_ids and rag_document_ids")."""
        return f"{self.source_file}#{self.heading}"


def retrieve(query: str, top_k: int = 3, min_score: float = 0.05) -> list[RetrievedChunk]:
    """Real lexical (BM25) retrieval over the curated knowledge base -- no
    embeddings, no external API call, entirely deterministic and offline,
    so it cannot fail on a missing credential or a rate limit the way an
    LLM call can. Returns [] (not an error, and not logged as one) when the
    knowledge base is empty or nothing scores above min_score -- an event
    with no relevant company/market context is a normal, honest outcome,
    not a failure to be papered over with an irrelevant top-1 result."""
    chunks = load_chunks()
    if not chunks:
        return []
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    scores = _bm25_scores(query_tokens, chunks)
    ranked = sorted(zip(chunks, scores), key=lambda pair: -pair[1])

    results: list[RetrievedChunk] = []
    for chunk, score in ranked[:top_k]:
        if score < min_score:
            continue
        results.append(RetrievedChunk(source_file=chunk.source_file, heading=chunk.heading, text=chunk.text, score=round(score, 4)))
    return results
