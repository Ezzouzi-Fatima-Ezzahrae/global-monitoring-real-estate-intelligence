"""Tests for src/services/knowledge_base.py (Phase 4 RAG retrieval).

These tests build their own tiny, throwaway knowledge base under tmp_path
and point the module at it via monkeypatch -- they must never depend on
the real project knowledge_base/ folder's actual content, which is real,
sourced material that keeps growing and changing (see knowledge_base/README.md).
A wording change in a real knowledge-base file should never make one of
these tests start or stop passing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from src.services import knowledge_base


@pytest.fixture(autouse=True)
def _reset_cache():
    """load_chunks() caches in a module-level global -- reset it before and
    after every test so one test's fake knowledge base never leaks into
    another's, and so each test's monkeypatched KNOWLEDGE_BASE_DIR is
    actually the one read (a stale cache would silently keep serving an
    earlier test's directory)."""
    knowledge_base._CACHE = None
    yield
    knowledge_base._CACHE = None


def _write(root: Path, name: str, content: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_chunks_splits_on_h2_headings(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_BASE_DIR", tmp_path)
    _write(tmp_path, "company/example.md", (
        "# Example Company File\n\n"
        "## Section One\n\nSome real content about zoning permits.\n\n"
        "## Section Two\n\nSome other real content about villa pricing.\n"
    ))
    chunks = knowledge_base.load_chunks(force_reload=True)
    assert len(chunks) == 2
    assert chunks[0].heading == "Section One"
    assert "zoning permits" in chunks[0].text
    assert chunks[0].source_file == "company/example.md"
    assert chunks[1].heading == "Section Two"
    assert "villa pricing" in chunks[1].text


def test_load_chunks_ignores_content_before_the_first_h2(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_BASE_DIR", tmp_path)
    _write(tmp_path, "orphan.md", (
        "# Title\n\nThis intro paragraph is not under any ## heading.\n\n"
        "## Real Section\n\nThis is retrievable.\n"
    ))
    chunks = knowledge_base.load_chunks(force_reload=True)
    assert len(chunks) == 1
    assert "intro paragraph" not in chunks[0].text
    assert "retrievable" in chunks[0].text


def test_load_chunks_skips_readme(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_BASE_DIR", tmp_path)
    _write(tmp_path, "README.md", "# Knowledge Base\n\n## Files\n\nThis should never be retrieved.\n")
    _write(tmp_path, "real.md", "# Real\n\n## A Section\n\nThis should be retrieved.\n")
    chunks = knowledge_base.load_chunks(force_reload=True)
    assert len(chunks) == 1
    assert chunks[0].source_file == "real.md"


def test_load_chunks_returns_empty_list_when_directory_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_BASE_DIR", tmp_path / "does_not_exist")
    assert knowledge_base.load_chunks(force_reload=True) == []


def test_retrieve_ranks_the_matching_chunk_first(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_BASE_DIR", tmp_path)
    _write(tmp_path, "market.md", (
        "# Market\n\n"
        "## Villa Prices Palmeraie\n\nLuxury villa prices in the Palmeraie neighborhood "
        "of Marrakech have risen due to strong demand from foreign buyers.\n\n"
        "## Tourism Arrivals\n\nMorocco tourist arrivals increased this year according to "
        "official figures from the tourism ministry.\n"
    ))
    results = knowledge_base.retrieve("Palmeraie villa demand from foreign buyers", top_k=1)
    assert len(results) == 1
    assert results[0].heading == "Villa Prices Palmeraie"
    assert results[0].score > 0


def test_retrieve_returns_empty_list_when_nothing_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_BASE_DIR", tmp_path)
    _write(tmp_path, "market.md", "# Market\n\n## Villa Prices\n\nLuxury villa prices in Marrakech.\n")
    results = knowledge_base.retrieve("unrelated topic about deep sea fishing quotas", top_k=3)
    assert results == []


def test_retrieve_respects_top_k(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_BASE_DIR", tmp_path)
    _write(tmp_path, "market.md", (
        "# Market\n\n"
        "## Section A\n\nMarrakech villa prices rose in the Palmeraie this quarter.\n\n"
        "## Section B\n\nMarrakech villa prices in Amelkis also rose this quarter.\n\n"
        "## Section C\n\nMarrakech villa prices in Targa were roughly flat this quarter.\n"
    ))
    results = knowledge_base.retrieve("Marrakech villa prices this quarter", top_k=2)
    assert len(results) == 2


def test_retrieve_on_empty_knowledge_base_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_BASE_DIR", tmp_path)
    assert knowledge_base.retrieve("anything at all", top_k=3) == []


def test_retrieve_on_blank_query_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_BASE_DIR", tmp_path)
    _write(tmp_path, "market.md", "# Market\n\n## Section\n\nSome real content here.\n")
    assert knowledge_base.retrieve("   ", top_k=3) == []


def test_citation_combines_source_file_and_heading(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "KNOWLEDGE_BASE_DIR", tmp_path)
    _write(tmp_path, "company/land.md", "# Land\n\n## Parcel One\n\nA real, specific parcel description.\n")
    results = knowledge_base.retrieve("real specific parcel description", top_k=1)
    assert len(results) == 1
    assert results[0].citation == "company/land.md#Parcel One"
