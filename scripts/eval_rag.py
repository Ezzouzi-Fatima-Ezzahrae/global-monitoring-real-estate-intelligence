"""Offline evaluation of the knowledge-base retrieval (BM25).

Measures, on a hand-written golden set, how often the expected knowledge-base
file shows up in the top-k results (recall@k), how high it ranks (MRR), and
whether the retrieval honestly returns nothing for questions the knowledge
base cannot answer. It changes no production code: it only calls
knowledge_base.retrieve() and compares variants.

    python -m scripts.eval_rag                  # baseline
    python -m scripts.eval_rag --variant alias  # query expansion with an alias table
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Callable

GOLDEN_SET_DEFAULT = Path(__file__).resolve().parents[1] / "eval" / "rag_golden_set.json"


# --------------------------------------------------------------------------
# Golden set
# --------------------------------------------------------------------------
def load_cases(path: Path) -> list[dict]:
    """Loads and validates the golden set. Fails loudly on a malformed case
    instead of silently scoring it as a miss."""
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate case ids in the golden set")
    for c in cases:
        if c["kind"] == "negative":
            if c.get("expected"):
                raise ValueError(f"negative case {c['id']} must not list expected files")
        elif not c.get("expected"):
            raise ValueError(f"case {c['id']} has no expected file")
    return cases


# --------------------------------------------------------------------------
# Metrics (pure functions: no knowledge base needed, easy to unit-test)
# --------------------------------------------------------------------------
def first_hit_rank(citations: list[str], expected: list[str]) -> int | None:
    """1-based rank of the first citation that contains any expected file stem,
    or None if no result matches."""
    for rank, citation in enumerate(citations, start=1):
        if any(stem.lower() in citation.lower() for stem in expected):
            return rank
    return None


def evaluate(cases: list[dict], retrieve: Callable[[str, int], list], k: int = 3) -> list[dict]:
    """`retrieve(query, k)` returns objects with a `.citation` attribute, the
    same shape knowledge_base.retrieve() returns to the Judge stage."""
    rows = []
    for case in cases:
        citations = [str(r.citation) for r in retrieve(case["query"], k)]
        if case["kind"] == "negative":
            # Correct behaviour for an unanswerable question: return nothing.
            rank, ok = None, len(citations) == 0
        else:
            rank = first_hit_rank(citations, case["expected"])
            ok = rank is not None
        rows.append({
            "id": case["id"], "kind": case["kind"], "query": case["query"],
            "expected": case.get("expected", []), "rank": rank, "ok": ok, "citations": citations,
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    positives = [r for r in rows if r["kind"] != "negative"]
    negatives = [r for r in rows if r["kind"] == "negative"]
    summary: dict = {
        "n_positive": len(positives),
        "n_negative": len(negatives),
        "recall": sum(r["ok"] for r in positives) / len(positives) if positives else None,
        "mrr": sum(1 / r["rank"] for r in positives if r["rank"]) / len(positives) if positives else None,
        "abstention": sum(r["ok"] for r in negatives) / len(negatives) if negatives else None,
        "recall_by_kind": {},
        #21/10/2026
        # A miss that still returned something is worse for the Judge than a silent
        # one: it reads the unrelated chunk as if it were context.
        "false_hits": sum(1 for r in positives if not r["ok"] and r["citations"]),
    }
    for kind in sorted({r["kind"] for r in positives}):
        subset = [r for r in positives if r["kind"] == kind]
        summary["recall_by_kind"][kind] = sum(r["ok"] for r in subset) / len(subset)
    return summary


# --------------------------------------------------------------------------
# Variant B: query expansion with a small alias table
# --------------------------------------------------------------------------
def normalize(text: str) -> str:
    """Lower-case and strip accents/diacritics (also Arabic tashkeel), so that
    'arrivées' and 'arrivees' match the same alias key."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


# French/Arabic term -> English words to append to the query. Only valid if the
# knowledge-base files are written in English: check this before trusting it.
ALIASES: dict[str, str] = {
    "maroc": "morocco",
    "marocain": "moroccan",
    "المغرب": "morocco",
    "marrakech": "marrakesh",
    "touristes": "tourists visitors",
    "السياح": "tourists visitors",
    "tourisme": "tourism",
    "arrivees": "arrivals",
    "taux directeur": "policy rate interest rate",
    "سعر الفائدة": "interest rate",
    "banque centrale": "central bank bank al-maghrib",
    "croissance": "growth gdp",
    "immobilier": "real estate property",
    "العقار": "real estate property",
    "prix": "prices",
    "loyers": "rental rents",
    "rendement locatif": "rental yield",
    "pandemie": "pandemic covid",
    "كوفيد": "covid pandemic",
}
_NORMALIZED_ALIASES = {normalize(k): v for k, v in ALIASES.items()}


def expand_query(query: str, aliases: dict[str, str] = _NORMALIZED_ALIASES) -> str:
    """Appends the English equivalents of any alias found in the query. The
    original query is kept, so nothing that matched before can stop matching."""
    normalized = normalize(query)
    extra = [
        english for key, english in aliases.items()
        if re.search(rf"(?<!\w){re.escape(key)}(?!\w)", normalized)
    ]
    return query if not extra else query + " " + " ".join(extra)


# --------------------------------------------------------------------------
# Variant E (later): reciprocal rank fusion of two rankings
# --------------------------------------------------------------------------
def rrf(rankings: list[list[str]], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion: a document ranked well by at least one method
    rises. k=60 is the value from the original paper."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=scores.get, reverse=True)


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------
#21/10/2026
def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def format_report(name: str, rows: list[dict], k: int) -> str:
    """Builds the report as text, so it can be printed AND written to a UTF-8
    file by Python itself (see main): shell redirection on Windows re-encodes
    the output and breaks on Arabic queries."""
    s = summarize(rows)
    lines = [f"=== {name} (k={k}) ==="]
    for r in rows:
        if not r["ok"]:
            lines.append(f"MISS [{r['kind']}] {r['id']}: {r['query'][:60]!r}")
            lines.append(f"     expected={r['expected']} got={r['citations']}")
    lines.append(
        f"recall@{k}={_fmt(s['recall'])}  MRR={_fmt(s['mrr'])}  abstention={_fmt(s['abstention'])}"
        f"  (positives={s['n_positive']}, negatives={s['n_negative']})"
    )
    lines.append(f"  false hits: {s['false_hits']} (a miss that returned an unrelated chunk instead of nothing)")
    for kind, value in s["recall_by_kind"].items():
        lines.append(f"  recall by kind: {kind:<11} {value:.2f}")
    return "\n".join(lines)


def compare_table(results: list[tuple[str, dict]]) -> str:
    """One markdown row per run: [(label, summary), ...]."""
    lines = ["| Run | recall@k | MRR | abstention | false hits |", "|---|---|---|---|---|"]
    for label, s in results:
        lines.append(
            f"| {label} | {_fmt(s['recall'])} | {_fmt(s['mrr'])} | {_fmt(s['abstention'])} | {s['false_hits']} |"
        )
    return "\n".join(lines)


def run_all(golden_sets: dict[str, list[dict]], variants: dict[str, Callable], k: int) -> list[tuple[str, list[dict]]]:
    """Every variant on every golden set, so a comparison is one command and
    no result file is produced at the wrong moment."""
    runs = []
    for set_name, cases in golden_sets.items():
        for variant_name, retrieve in variants.items():
            runs.append((f"{variant_name} / {set_name}", evaluate(cases, retrieve, k)))
    return runs


HELDOUT_DEFAULT = Path(__file__).resolve().parents[1] / "eval" / "rag_golden_set_heldout.json"


def main() -> None:
    import sys

    from src.services import knowledge_base  # imported here so the pure functions need no project setup

    # A redirected stdout on Windows defaults to cp1252, which cannot encode the
    # Arabic queries (or some characters in citations): force UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", type=Path, default=GOLDEN_SET_DEFAULT)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--variant", choices=["baseline", "alias"], default="baseline")
    parser.add_argument("--all", action="store_true", help="baseline and alias, on the golden set and the held-out set")
    parser.add_argument("--out", type=Path, default=None, help="also write the report to this UTF-8 file")
    args = parser.parse_args()

    plain = lambda q, k: knowledge_base.retrieve(q, top_k=k)
    expanded = lambda q, k: knowledge_base.retrieve(expand_query(q), top_k=k)

    if args.all:
        golden_sets = {"golden": load_cases(args.golden)}
        if HELDOUT_DEFAULT.exists():
            golden_sets["held-out"] = load_cases(HELDOUT_DEFAULT)
        runs = run_all(golden_sets, {"baseline": plain, "alias": expanded}, args.k)
        parts = [format_report(label, rows, args.k) for label, rows in runs]
        parts.append(compare_table([(label, summarize(rows)) for label, rows in runs]))
        report = "\n\n".join(parts)
    else:
        retrieve = expanded if args.variant == "alias" else plain
        report = format_report(args.variant, evaluate(load_cases(args.golden), retrieve, args.k), args.k)

    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()