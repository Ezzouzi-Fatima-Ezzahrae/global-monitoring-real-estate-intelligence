"""Guards the knowledge base against content the chunker silently drops.

src/services/knowledge_base.py indexes only the text under a level-2 ("## ")
heading. Anything between the "# " title and the first "## " is never indexed,
so a file written as a title followed directly by bullets is invisible to the
Judge. The retrieval evaluation (scripts/eval_rag.py) found exactly this:
tourism_stats.md had its figures before the first "## " and no query could
retrieve them.

If the chunker ever starts indexing that leading text, this test should be
removed together with that change.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.services import knowledge_base


def _unindexed_lines(path: Path) -> list[str]:
    """Non-empty lines before the first '## ' heading, ignoring the '# ' title
    and '>' provenance notes (neither carries facts the Judge needs)."""
    lost = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            break
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", ">")):
            lost.append(stripped)
    return lost


def test_no_knowledge_file_has_content_before_its_first_level_2_heading():
    problems = {}
    for path in sorted(knowledge_base.KNOWLEDGE_BASE_DIR.rglob("*.md")):
        if path.name.upper() == "README.MD":
            continue  # the human-facing index, not loaded by the retrieval
        lost = _unindexed_lines(path)
        if lost:
            problems[path.name] = lost[:2]
    assert not problems, f"content the chunker never indexes (add a '## ' heading above it): {problems}"