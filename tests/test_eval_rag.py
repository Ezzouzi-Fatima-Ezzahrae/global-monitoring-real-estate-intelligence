import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.eval_rag import (compare_table, evaluate, expand_query, first_hit_rank, format_report, load_cases, normalize, rrf, run_all, summarize)


def _fake_retrieve(table):
    """Builds a retrieve(query, k) that returns canned citations per query."""
    def retrieve(query, k):
        return [SimpleNamespace(citation=c) for c in table.get(query, [])][:k]
    return retrieve


CASES = [
    {"id": "d1", "kind": "direct", "query": "q1", "expected": ["tourism_stats"]},
    {"id": "d2", "kind": "direct", "query": "q2", "expected": ["macro_morocco"]},
    {"id": "c1", "kind": "cross_lang", "query": "q3", "expected": ["macro_morocco"]},
    {"id": "n1", "kind": "negative", "query": "q4", "expected": []},
    {"id": "n2", "kind": "negative", "query": "q5", "expected": []},
]


def test_first_hit_rank_is_one_based_and_none_when_absent():
    assert first_hit_rank(["a.md#1", "tourism_stats.md#2"], ["tourism_stats"]) == 2
    assert first_hit_rank(["a.md#1"], ["tourism_stats"]) is None
    assert first_hit_rank([], ["x"]) is None


def test_metrics_on_a_known_table():
    retrieve = _fake_retrieve({
        "q1": ["tourism_stats.md#1"],                       # rank 1
        "q2": ["other.md#1", "macro_morocco.md#2"],         # rank 2
        "q3": ["other.md#1", "other.md#2", "other.md#3"],   # miss
        "q4": [],                                           # correct abstention
        "q5": ["tourism_stats.md#1"],                       # should have abstained
    })
    s = summarize(evaluate(CASES, retrieve, k=3))
    assert s["recall"] == pytest.approx(2 / 3)
    assert s["mrr"] == pytest.approx((1 + 0.5 + 0) / 3)
    assert s["abstention"] == pytest.approx(0.5)
    assert s["recall_by_kind"] == {"cross_lang": 0.0, "direct": 1.0}
    #21/10/2026
    assert s["false_hits"] == 1          # q3: a miss that still returned unrelated chunks


def test_k_limits_which_results_count():
    retrieve = _fake_retrieve({"q1": ["x#1", "y#1", "tourism_stats#1"]})
    case = [{"id": "d1", "kind": "direct", "query": "q1", "expected": ["tourism_stats"]}]
    assert summarize(evaluate(case, retrieve, k=2))["recall"] == 0.0
    assert summarize(evaluate(case, retrieve, k=3))["recall"] == 1.0


def test_load_cases_rejects_bad_golden_sets(tmp_path):
    def write(cases):
        p = tmp_path / "g.json"
        p.write_text(json.dumps(cases), encoding="utf-8")
        return p
    with pytest.raises(ValueError):
        load_cases(write([{"id": "a", "kind": "direct", "query": "q", "expected": []}]))
    with pytest.raises(ValueError):
        load_cases(write([{"id": "a", "kind": "negative", "query": "q", "expected": ["x"]}]))
    with pytest.raises(ValueError):
        load_cases(write([{"id": "a", "kind": "direct", "query": "q", "expected": ["x"]},
                          {"id": "a", "kind": "direct", "query": "q2", "expected": ["x"]}]))


def test_normalize_strips_accents_and_case():
    assert normalize("Arrivées") == "arrivees"


def test_expand_query_adds_english_terms_and_keeps_the_original():
    out = expand_query("arrivées de touristes au Maroc")
    assert out.startswith("arrivées de touristes au Maroc")
    for word in ("arrivals", "tourists", "morocco"):
        assert word in out


def test_expand_query_matches_whole_words_only_and_leaves_english_alone():
    assert expand_query("tourist arrivals to Morocco") == "tourist arrivals to Morocco"
    assert expand_query("prixime") == "prixime"   # 'prix' inside another word must not fire


def test_expand_query_handles_arabic_and_multiword_keys():
    assert "interest rate" in expand_query("سعر الفائدة الرئيسي")
    assert "policy rate" in expand_query("Le taux directeur baisse")


def test_rrf_promotes_documents_ranked_well_by_either_method():
    fused = rrf([["a", "b", "c"], ["c", "d", "a"]])
    assert fused[0] == "a" and set(fused) == {"a", "b", "c", "d"}
    assert fused.index("c") < fused.index("b")

def test_format_report_lists_misses_and_survives_arabic_text():
    cases = [
        {"id": "c-05", "kind": "cross_lang", "query": "سعر الفائدة الرئيسي لبنك المغرب", "expected": ["macro_morocco"]},
        {"id": "d-02", "kind": "direct", "query": "interest rate", "expected": ["macro_morocco"]},
    ]
    retrieve = _fake_retrieve({"interest rate": ["macro_morocco.md#Rates"]})
    text = format_report("baseline", evaluate(cases, retrieve, k=3), 3)
    assert "MISS [cross_lang] c-05" in text
    assert "d-02" not in text                      # only misses are listed
    assert "recall@3=0.50" in text
    text.encode("utf-8")                           # must be writable as UTF-8

#21/10/2026
def test_false_hits_count_only_misses_that_returned_something():
    cases = [
        {"id": "a", "kind": "direct", "query": "qa", "expected": ["x"]},   # miss, silent
        {"id": "b", "kind": "direct", "query": "qb", "expected": ["x"]},   # miss, unrelated chunk
        {"id": "c", "kind": "direct", "query": "qc", "expected": ["x"]},   # hit
    ]
    retrieve = _fake_retrieve({"qb": ["other.md#1"], "qc": ["x.md#1"]})
    s = summarize(evaluate(cases, retrieve, k=3))
    assert s["false_hits"] == 1 and s["recall"] == pytest.approx(1 / 3)


def test_run_all_and_compare_table_cover_every_variant_on_every_set():
    sets = {"golden": CASES[:1], "held-out": CASES[1:2]}
    good = _fake_retrieve({"q1": ["tourism_stats#1"], "q2": ["macro_morocco#1"]})
    silent = _fake_retrieve({})
    runs = run_all(sets, {"good": good, "silent": silent}, k=3)
    assert [label for label, _ in runs] == [
        "good / golden", "silent / golden", "good / held-out", "silent / held-out",
    ]
    table = compare_table([(label, summarize(rows)) for label, rows in runs])
    assert table.count("\n") == 5                      # header, separator, 4 rows
    assert "| good / golden | 1.00 |" in table and "| silent / held-out | 0.00 |" in table