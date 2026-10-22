# Knowledge-base retrieval evaluation

## Setup
- BM25 (current), alias expansion, semantic (paraphrase-multilingual-MiniLM-L12-v2, local, threshold 0.40), hybrid (RRF).
- Sets: golden (19), held-out (10), extra (10). Metrics: recall@3, MRR, abstention, false hits.
- Versions: sentence-transformers X, torch Y. max_seq_length = Z.

## Results
(the comparison table from eval/results_summary.md and eval/semantic_result_extra.md)

## Findings
1. Two files (tourism_stats, listings) had content the chunker never indexed (fixed; see the index PR).
2. Cross-language queries return nothing with BM25 (held-out recall 0.25).
3. Hybrid is best on the golden set (1.00 / 0.92, no false hit); semantic alone misses
   "COVID-19 impact..." because meaning dominates an exact term.

## Limits
- Held-out is cross-language only and was written by the same person as the alias table.
- Few negatives, and the first ones were easy; the extra set adds hard ones.
- Chunks longer than max_seq_length are truncated.
- Company files are not evaluated. Public files only.

## Decision (for the maintainer)
Options: alias table (no dependency) / hybrid with a local model (471 MB model + PyTorch, conflicts with NFR-05)
/ nothing. Not adopted in production by this PR.