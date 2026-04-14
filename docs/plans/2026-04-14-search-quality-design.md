# Search quality redesign — Level 1 lexical

**Date:** 2026-04-14
**Branch:** `soft-search`
**Scope:** Level 1 lexical search only. Level 2 (semantic) untouched.

## Problem

Baseline on 9 golden queries (`scripts/search_baseline.py`,
`tasks/soft-search-baseline.md`) shows three systemic quality issues:

1. **Prefix `:*` on short tokens creates false matches.**
   `лабораторные по физике` → top-1 is `Растворение как физико-химический
   процесс` because `физик:*` hits `физико-`.
2. **OR-tsquery weights tokens equally.** `2 закон ньютона` → top-1 is
   `Закон больших чисел. Вариант 2` because `закон` is dense, while
   `ньютон` — the rare, specific token — gets no extra weight.
3. **Stop words (`по`, `к`, `на`, ...) are kept in the OR-query**,
   diluting the signal and adding useless matches.

Additionally, the trigram-on-title leg (`pg_trgm`) adds noise without
helping: on multi-word queries `similarity()` on the full phrase plateaus
(`лабораторные по физике` → sim ≤ 0.21 on unrelated rows).

One query (`пушкин`) is a **content ceiling**, not an algorithm bug — the
6 matching lessons live in `description` only. Separate task (`ts_headline`
snippet in UI).

## Design

Level 1 `fts_search_fuzzy` becomes a single-CTE FTS search with
IDF-weighted token scoring. No trigram. No prefix.

### Pipeline

1. **Tokenize + filter stop words.** New `_STOPWORDS` set
   (`по, к, на, и, в, с, от, для, о, об, при, через, над, под, без, из, у`).
   Applied after lowercase + punctuation strip; before tsquery build.
2. **Build OR-tsquery, exact tokens only.** No `:*`. Russian Snowball
   stemmer in `to_tsquery('russian', ...)` already handles morphology
   (`ньютона → ньютон`, `законы → закон`, `физике → физик`). Digit tokens
   stay literal (already done today).
3. **Per-query IDF.** For each surviving token, run
   `SELECT count(*) FROM lessons WHERE search_vector @@ to_tsquery('russian', :tok)`
   once. Compute `w = ln((N + 1) / (df + 1)) + 1`. N cached at service
   init or re-fetched per query (cheap: one `count(*)` on `lessons`).
4. **Score rows by sum of IDF weights of matching tokens.** One SQL:

   ```sql
   SELECT l.id,
          (CASE WHEN l.search_vector @@ to_tsquery('russian', :tok0) THEN :w0 ELSE 0 END)
        + (CASE WHEN l.search_vector @@ to_tsquery('russian', :tok1) THEN :w1 ELSE 0 END)
        + ... AS score
   FROM lessons l
   WHERE l.search_vector @@ to_tsquery('russian', :or_ts)
   ORDER BY (CASE WHEN l.url = 'N/A' THEN 1 ELSE 0 END), score DESC, l.id
   ```

   Each `CASE` hits the GIN index (one short tsquery per token). The
   outer `WHERE` narrows rows first, so per-token checks run on the
   candidate set, not the full table.

### Removed

- CTE `trg` and all `pg_trgm` similarity code in `fts_search_fuzzy`.
- Settings: `trigram_similarity_threshold`, `trigram_title_weight`.
  (Keep `fts_score_floor` dead for now — delete alongside code.)
- Prefix `:*` builder logic (keep digit-vs-word branching as-is, minus
  the `:*`).
- Tests referencing trigram thresholds or prefix matching.

### Kept

- `ENABLE_FUZZY_SEARCH` flag — toggles between new IDF path and the
  strict AND `plainto_tsquery` rollback (`fts_search`). Rollback lane
  stays untouched.
- Abbreviation filters (`_abbr_filters`) — independent feature for ВПР,
  ОГЭ, ЕГЭ. Unchanged.
- Level 2 pipeline (`_build_level_results`, `semantic_search`).
- `fts_search_all_fuzzy` paginator wrapper, just calls the new fuzzy.

## Expected impact on the 9 queries

| Query | Before top-1 | Expected after |
|---|---|---|
| `пушкин` | OGE task | same (content ceiling, 6 rows) |
| `петр 1` | Российская империя 1п. XVIII | петровская реформа (IDF of `петр` > `1`) |
| `2 закон ньютона` | Закон больших чисел | **Второй/третий законы Ньютона** (IDF of `ньютон` ≫ `закон`) |
| `подготовка к ЕГЭ по физике` | EGE linia №18 | ЕГЭ физика (stop words out; `ЕГЭ`, `физик` dominate) |
| `впр по химии` | ВПР химия 8кл | same/cleaner (top stays good, #5 noise drops) |
| `великая отечественная война` | ВОВ окруж.мир | same (already good) |
| `лабораторные по физике` | Растворение (химия) | лабораторные-в-title (physics) if any; else EGE-по-физике (no `физико-` hit) |
| `лабораторные` | правила работы в лаб. | same (single rare token; already OK) |
| `лабораторные работы` | правила работы в лаб. | same |

`пушкин` and `лабораторные*` bounded by content; rest gets sharper.

## Testing

- Unit: `_normalize_tokens` filters stop words; OR-tsquery has no `:*`.
- Unit: IDF helper returns higher weight for rare token than frequent.
- Integration (against dev DB, gated on env): rerun
  `scripts/search_baseline.py`, diff against saved baseline, assert
  specific ranking checks on the 3 showcase queries:
  - `2 закон ньютона` → `Масса. Сила. Второй и третий законы Ньютона`
    in top-3.
  - `лабораторные по физике` → top-3 contains no `физико-химический`
    rows.
  - `петр 1` → top-3 contains at least one lesson with `Петр` / `Пётр`
    in title.

## Non-goals

- Speed (separate task — L1 still ~500ms median; expect 1 extra token
  roundtrip for IDF but no change in worst case).
- Level 2 semantic query latency.
- `ts_headline` description snippets (separate UI task).
- Typo tolerance (trigram removed; revisit only if metric regression on
  real traffic).
- Content coverage (Pushkin-in-title problem).

## Rollback

One setting: `ENABLE_FUZZY_SEARCH=false` → back to strict AND path.
