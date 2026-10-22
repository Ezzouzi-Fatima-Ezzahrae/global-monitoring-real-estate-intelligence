import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.eval_rag import evaluate, summarize
from scripts.eval_rag_semantic import cosine, make_retrievers, semantic_rank

# A fake 3-dimensional "embedding": axis 0 = tourism, 1 = interest rates, 2 = covid.
CITATIONS = ["tourism_stats.md#Figures", "macro_morocco.md#Monetary Policy", "historical_precedents.md#Recovery"]
CHUNK_VECS = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
VECTORS = {
    "arrivees de touristes": [0.9, 0.1, 0.0],     # French tourism question
    "taux directeur": [0.1, 0.9, 0.0],            # French rate question
    "recette de cuisine": [0.34, 0.33, 0.33],     # off-topic: close to nothing in particular
}


def fake_encode(texts):
    return [VECTORS[t] for t in texts]


def test_cosine_basics():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([0, 0], [1, 0]) == 0.0


def test_semantic_rank_orders_by_similarity_and_applies_the_threshold():
    ranked = semantic_rank([0.9, 0.1, 0.0], CHUNK_VECS, CITATIONS, min_similarity=0.5)
    assert [c for c, _ in ranked] == ["tourism_stats.md#Figures"]
    everything = semantic_rank([0.9, 0.1, 0.0], CHUNK_VECS, CITATIONS, min_similarity=0.0)
    assert everything[0][0] == "tourism_stats.md#Figures" and len(everything) == 3


def _retrievers(threshold, bm25=None):
    bm25 = bm25 or {}
    return make_retrievers(CITATIONS, CHUNK_VECS, fake_encode, lambda q: bm25.get(q, []), threshold)


def test_semantic_finds_a_question_with_no_shared_word_and_bm25_stays_silent():
    r = _retrievers(0.5)
    assert [h.citation for h in r["semantic"]("arrivees de touristes", 3)] == ["tourism_stats.md#Figures"]
    assert r["bm25"]("arrivees de touristes", 3) == []


def test_threshold_keeps_the_abstention_on_an_off_topic_question():
    assert _retrievers(0.7)["semantic"]("recette de cuisine", 3) == []
    # a threshold that is too low turns every question into a hit: this is what the sweep guards against
    assert len(_retrievers(0.1)["semantic"]("recette de cuisine", 3)) == 3


def test_hybrid_fuses_both_rankings_and_stays_silent_when_both_are():
    r = _retrievers(0.5, bm25={"taux directeur": ["historical_precedents.md#Recovery"]})
    fused = [h.citation for h in r["hybrid"]("taux directeur", 3)]
    assert set(fused) == {"historical_precedents.md#Recovery", "macro_morocco.md#Monetary Policy"}
    assert _retrievers(0.7)["hybrid"]("recette de cuisine", 3) == []


def test_the_evaluator_accepts_these_retrievers():
    cases = [
        {"id": "c1", "kind": "cross_lang", "query": "arrivees de touristes", "expected": ["tourism_stats"]},
        {"id": "n1", "kind": "negative", "query": "recette de cuisine", "expected": []},
    ]
    s = summarize(evaluate(cases, _retrievers(0.7)["semantic"], k=3))
    assert s["recall"] == 1.0 and s["abstention"] == 1.0