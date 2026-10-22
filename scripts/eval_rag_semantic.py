"""Offline comparison of BM25 against semantic and hybrid retrieval.

Research script: it changes no production code and needs a sentence-embedding
model that is NOT in requirements.txt (see the install note in the PR). The
model runs locally, so no knowledge-base text leaves the machine (NFR-04).

    python -m scripts.eval_rag_semantic --sweep               # pick a threshold on the golden set
    python -m scripts.eval_rag_semantic --threshold 0.40      # then report on both sets
"""
from __future__ import annotations

import argparse
import math
from collections import namedtuple
from pathlib import Path
from typing import Callable

from scripts.eval_rag import (GOLDEN_SET_DEFAULT, HELDOUT_DEFAULT, compare_table, evaluate, format_report,
                              load_cases, rrf, summarize)

Hit = namedtuple("Hit", "citation score")

# To verify before relying on it: a multilingual sentence-embedding model.
DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"


# --------------------------------------------------------------------------
# Pure functions (tested with a fake encoder, no model needed)
# --------------------------------------------------------------------------
def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def semantic_rank(query_vec: list[float], chunk_vecs: list[list[float]], citations: list[str],
                  min_similarity: float) -> list[tuple[str, float]]:
    """Chunks sorted by cosine similarity, keeping only those at or above the
    threshold. The threshold is what lets this retrieval stay silent: an
    embedding always has a nearest neighbour, BM25 does not."""
    scored = [(cit, cosine(query_vec, vec)) for cit, vec in zip(citations, chunk_vecs)]
    kept = [(cit, sim) for cit, sim in scored if sim >= min_similarity]
    return sorted(kept, key=lambda pair: -pair[1])


def make_retrievers(citations: list[str], chunk_vecs: list[list[float]], encode: Callable[[list[str]], list[list[float]]],
                    bm25_citations: Callable[[str], list[str]], threshold: float) -> dict[str, Callable]:
    """Builds the three retrieve(query, k) functions the evaluator expects.
    `encode` maps texts to vectors; `bm25_citations` returns the BM25 ranking
    (already filtered by the knowledge base's own minimum score)."""
    cache: dict[str, list[float]] = {}

    def query_vec(q: str) -> list[float]:
        if q not in cache:
            cache[q] = encode([q])[0]
        return cache[q]

    def semantic(q: str, k: int) -> list[Hit]:
        ranked = semantic_rank(query_vec(q), chunk_vecs, citations, threshold)
        return [Hit(c, s) for c, s in ranked[:k]]

    def hybrid(q: str, k: int) -> list[Hit]:
        sem = [c for c, _ in semantic_rank(query_vec(q), chunk_vecs, citations, threshold)]
        fused = rrf([bm25_citations(q), sem])   # both empty -> nothing: abstention is kept
        return [Hit(c, 0.0) for c in fused[:k]]

    def bm25(q: str, k: int) -> list[Hit]:
        return [Hit(c, 0.0) for c in bm25_citations(q)[:k]]

    return {"bm25": bm25, "semantic": semantic, "hybrid": hybrid}


# --------------------------------------------------------------------------
# Command line (needs the project and the embedding model)
# --------------------------------------------------------------------------
def build_encoder(model_name: str) -> Callable[[list[str]], list[list[float]]]:
    from sentence_transformers import SentenceTransformer  # imported here: not a project dependency

    model = SentenceTransformer(model_name)
    return lambda texts: model.encode(texts, normalize_embeddings=True).tolist()


def main() -> None:
    import sys

    from src.services import knowledge_base as kb

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--threshold", type=float, default=0.40)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--sweep", action="store_true", help="semantic-only, thresholds 0.20..0.60, golden set")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    chunks = kb.load_chunks()
    citations = [f"{c.source_file}#{c.heading}" for c in chunks]
    encode = build_encoder(args.model)
    # The model truncates long chunks (for example the big price tables): only the
    # start of each chunk is embedded. A known limit, to state in the report.
    chunk_vecs = encode([f"{c.heading}\n{c.text}" for c in chunks])
    bm25_citations = lambda q: [r.citation for r in kb.retrieve(q, top_k=50)]

    golden = {"golden": load_cases(GOLDEN_SET_DEFAULT)}
    if HELDOUT_DEFAULT.exists():
        golden["held-out"] = load_cases(HELDOUT_DEFAULT)

    if args.sweep:
        # Thresholds are chosen on the golden set only; the held-out set is for the final number.
        results = []
        for t in (0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60):
            semantic = make_retrievers(citations, chunk_vecs, encode, bm25_citations, t)["semantic"]
            results.append((f"semantic t={t:.2f} / golden", summarize(evaluate(golden["golden"], semantic, args.k))))
        report = compare_table(results)
    else:
        retrievers = make_retrievers(citations, chunk_vecs, encode, bm25_citations, args.threshold)
        runs = []
        for set_name, cases in golden.items():
            for name, retrieve in retrievers.items():
                runs.append((f"{name} t={args.threshold:.2f} / {set_name}", evaluate(cases, retrieve, args.k)))
        parts = [format_report(label, rows, args.k) for label, rows in runs]
        parts.append(compare_table([(label, summarize(rows)) for label, rows in runs]))
        report = "\n\n".join(parts)

    print(report)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()