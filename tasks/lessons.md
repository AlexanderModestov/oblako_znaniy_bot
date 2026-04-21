## Search — structural limits of pure FTS (2026-04-15)

Two classes of queries are not solvable by any FTS configuration alone:

1. **Numeric form mismatch.** `петр 1` vs stored `Пётр I`; `2 закон` vs
   stored `Второй закон`. Tokenizer treats `1` and `i` as unrelated tokens.
   Rely on L2 (semantic) or tell users to spell ordinals / Roman numerals.
2. **Vocabulary gap.** Users type intent words (`подготовка`) that are
   absent from both titles and descriptions. Classic semantic-search case.

When adding fields to `search_vector`, check subject/grade too — they live
in separate tables (`subjects`) and tokens like «физика» may be missing
from `title`/`description` even for obviously-physics lessons.

L2 (semantic) rescue is bounded by `semantic_similarity_threshold` and
embedding coverage. Observed on the golden set: `петр 1 → 2`,
`2 закон ньютона → 1`, `подготовка к ЕГЭ по физике → 0`. The design-doc
"truth" counts (17 / 8 / 36) reflect human labeling, not what L2 actually
returns with the current threshold. Integration-test thresholds lock the
observed baseline; tune the threshold if we want more rescue.
