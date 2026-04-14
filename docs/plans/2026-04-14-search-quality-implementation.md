# L1 Search Quality Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite Level 1 lexical search to rank by IDF-weighted token matches, remove the trigram fallback and the `:*` prefix on tsquery tokens, filter Russian stop words. Rely on the Snowball stemmer in `to_tsquery('russian', ...)` for morphology.

**Architecture:** Single SQL — `WHERE search_vector @@ to_tsquery('russian', or_ts)` narrows candidates; score is `Σ idf_i * (search_vector @@ to_tsquery(tok_i))`. Per-query IDF via one `count(*)` per token (fast via GIN index). Trigram CTE, `pg_trgm` settings, and score-floor config all deleted. Rollback stays via `ENABLE_FUZZY_SEARCH=false`.

**Tech Stack:** Python 3.11+, SQLAlchemy async, asyncpg, PostgreSQL FTS (`tsvector`, `to_tsquery`), pytest-asyncio.

**Design doc:** `docs/plans/2026-04-14-search-quality-design.md`.

**Baseline for before/after diffing:** `tasks/soft-search-baseline.md` (committed in `7f84a52`). After the implementation, rerun `python -m scripts.search_baseline` and replace the file; commit the delta alongside the final PR-prep commit so the diff tells the quality story.

---

## Task 1: Add stop-word filtering to `_normalize_tokens`

**Why first:** It's the simplest cut and its tests are pure — no DB, no async. Shrinks the token list for every downstream change.

**Files:**
- Modify: `src/core/services/search.py:28-41` — add `_STOPWORDS` constant and filter inside `_normalize_tokens`.
- Modify: `tests/test_search_normalize.py` — add new tests.

**Step 1.1: Add two failing tests**

Append to `tests/test_search_normalize.py`:

```python
def test_normalize_filters_russian_stopwords():
    assert _normalize_tokens("лабораторные по физике") == ["лабораторные", "физике"]


def test_normalize_keeps_only_stopwords_returns_empty():
    assert _normalize_tokens("по на в") == []
```

**Step 1.2: Run new tests, confirm they fail**

Run: `pytest tests/test_search_normalize.py::test_normalize_filters_russian_stopwords tests/test_search_normalize.py::test_normalize_keeps_only_stopwords_returns_empty -v`
Expected: both FAIL (token `по` still present).

**Step 1.3: Implement**

In `src/core/services/search.py`, add near the other module-level regexes (after line 31):

```python
_STOPWORDS = frozenset({
    "по", "к", "на", "и", "в", "с", "от", "для", "о", "об", "при",
    "через", "над", "под", "без", "из", "у", "же", "ли", "бы", "не",
    "а", "но", "или", "как", "что", "это", "то",
})
```

Then in `_normalize_tokens`, change the return line (currently `return [t for t in raw if t and (len(t) >= 2 or t.isdigit())]`) to:

```python
return [
    t for t in raw
    if t and (len(t) >= 2 or t.isdigit()) and t not in _STOPWORDS
]
```

**Step 1.4: Run normalize tests**

Run: `pytest tests/test_search_normalize.py -v`
Expected: all pass, including the two new ones.

**Step 1.5: Commit**

```bash
git add src/core/services/search.py tests/test_search_normalize.py
git commit -m "$(cat <<'EOF'
feat(search): strip Russian stop words from query tokens

Stop words (по, к, на, и, ...) dilute OR-tsquery scoring and bloat the
per-token coverage check. Filter them out in _normalize_tokens. Same list
is applied to both the tsquery build and any downstream per-token logic.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Drop prefix `:*` from OR tsquery builder

**Why:** Prefix on short tokens hits unrelated stems (`физ:*` → `физико-химический`). Stemmer already does morphology for real query words.

**Files:**
- Modify: `src/core/services/search.py:44-50` — `_build_or_tsquery_string`.
- Modify: `tests/test_search_normalize.py:24-29, 36-37` — rewrite prefix-expecting tests.

**Step 2.1: Update existing tests to new expected output (still failing against current code)**

In `tests/test_search_normalize.py`, replace the four affected tests:

```python
def test_build_or_tsquery_single_token():
    assert _build_or_tsquery_string(["теорема"]) == "теорема"


def test_build_or_tsquery_multi_tokens():
    assert _build_or_tsquery_string(["теорема", "пифагора"]) == "теорема | пифагора"


def test_build_or_tsquery_digit_no_prefix():
    assert _build_or_tsquery_string(["2", "закон"]) == "2 | закон"


def test_build_or_tsquery_all_digits():
    assert _build_or_tsquery_string(["7", "11"]) == "7 | 11"
```

(`test_build_or_tsquery_empty` stays as-is.)

**Step 2.2: Run them, confirm they fail**

Run: `pytest tests/test_search_normalize.py -v -k "build_or_tsquery"`
Expected: four tests FAIL with `':*'` in the actual value.

**Step 2.3: Rewrite `_build_or_tsquery_string`**

Replace the function body (lines 44-50 of `src/core/services/search.py`):

```python
def _build_or_tsquery_string(tokens: list[str]) -> str:
    """Build a tsquery OR-string. No prefix matching — the Russian Snowball
    stemmer inside to_tsquery already normalizes tokens to their stem form.
    Prefix matching was removed after it caused false matches on short
    tokens (физ:* → физико-химический, see baseline 2026-04-14)."""
    return " | ".join(tokens)
```

Also update the function docstring reference in the module docstring (lines 1-12) if it mentions prefix — it doesn't explicitly, so no change beyond the function itself.

**Step 2.4: Run all normalize tests**

Run: `pytest tests/test_search_normalize.py -v`
Expected: all pass.

**Step 2.5: Commit**

```bash
git add src/core/services/search.py tests/test_search_normalize.py
git commit -m "$(cat <<'EOF'
fix(search): drop :* prefix from OR tsquery tokens

Prefix matching let short tokens leak into unrelated stems (физ:* hit
физико-химический, flooding 'лабораторные по физике' with chemistry).
The Russian Snowball stemmer inside to_tsquery already does morphology
for the realistic query forms users send, so the prefix added noise
without buying recall.

Trade-off: typed partial words (e.g. 'лаборато') no longer match.
Acceptable — we were not supporting autocomplete anyway, and the
trigram leg is being removed in a follow-up commit.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add IDF helper

A small async helper that, given a session and a list of normalized tokens, returns a dict `{token: idf_weight}`. One `count(*)` per token + one `count(*)` on the table total.

**Files:**
- Modify: `src/core/services/search.py` — add `_compute_idf` helper below `_build_or_tsquery_string`.
- Modify: `tests/test_search.py` — add unit test that mocks the session.

**Step 3.1: Write failing unit test**

Append to `tests/test_search.py` (end of file):

```python
@pytest.mark.asyncio
async def test_compute_idf_rarer_token_gets_higher_weight():
    """Token with small df must get a strictly larger IDF than a token
    with large df, given the same corpus size."""
    from src.core.services.search import _compute_idf

    mock_session = MagicMock()
    # Scalar sequence: total_n, df_rare, df_common
    scalars = iter([1000, 5, 500])

    async def fake_execute(_q, _params=None):
        result = MagicMock()
        result.scalar = MagicMock(return_value=next(scalars))
        return result

    mock_session.execute = fake_execute

    weights = await _compute_idf(mock_session, ["ньютон", "закон"])

    assert weights["ньютон"] > weights["закон"]
    assert weights["ньютон"] > 0
    assert weights["закон"] > 0


@pytest.mark.asyncio
async def test_compute_idf_empty_tokens_returns_empty():
    from src.core.services.search import _compute_idf

    mock_session = MagicMock()
    mock_session.execute = AsyncMock()  # should never be called
    weights = await _compute_idf(mock_session, [])
    assert weights == {}
    mock_session.execute.assert_not_called()
```

**Step 3.2: Run, confirm fail**

Run: `pytest tests/test_search.py -v -k "compute_idf"`
Expected: FAIL — `ImportError: cannot import name '_compute_idf'`.

**Step 3.3: Implement**

In `src/core/services/search.py`, after `_build_or_tsquery_string` (around line 50), add:

```python
async def _compute_idf(session, tokens: list[str]) -> dict[str, float]:
    """Compute IDF weight per token against the ``lessons`` corpus.

    Uses the natural log smoothed formula ``ln((N + 1) / (df + 1)) + 1``:
    positive for any token (even one matching all rows, where it returns 1),
    and strictly monotonic — rarer tokens always outweigh common ones.

    One ``count(*)`` per token (GIN-indexed, cheap) plus one for N.
    """
    if not tokens:
        return {}
    import math

    from sqlalchemy import text

    total_row = await session.execute(text("SELECT COUNT(*) FROM lessons"))
    n = total_row.scalar() or 0

    weights: dict[str, float] = {}
    for tok in tokens:
        df_row = await session.execute(
            text(
                "SELECT COUNT(*) FROM lessons "
                "WHERE search_vector @@ to_tsquery('russian', cast(:tok as text))"
            ),
            {"tok": tok},
        )
        df = df_row.scalar() or 0
        weights[tok] = math.log((n + 1) / (df + 1)) + 1.0
    return weights
```

**Step 3.4: Run idf tests**

Run: `pytest tests/test_search.py -v -k "compute_idf"`
Expected: both PASS.

**Step 3.5: Commit**

```bash
git add src/core/services/search.py tests/test_search.py
git commit -m "$(cat <<'EOF'
feat(search): add per-query IDF helper for token weighting

Used by the upcoming fuzzy-search rewrite to let rare tokens (ньютон)
outweigh common ones (закон) in the OR-tsquery ranking. Weight formula
ln((N+1)/(df+1)) + 1 keeps every term strictly positive and monotonic.

Lookups run one count(*) per token against the GIN index — cheap
enough to do per query; cache later if profiling shows it matters.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Rewrite `fts_search_fuzzy` to use IDF, drop trigram CTE

This is the core change. Replace the 3-CTE SQL with a single query that scores rows by the sum of IDF weights of matching tokens.

**Files:**
- Modify: `src/core/services/search.py:116-207` — replace `fts_search_fuzzy` body.
- Modify: `src/core/services/search.py:68-77` — drop trigram settings from `__init__`.

**Step 4.1: Simplify `SearchService.__init__`**

Replace the body (lines 68-77) with:

```python
def __init__(self):
    settings = get_settings()
    self.fts_min_results = settings.fts_min_results
    self.similarity_threshold = settings.semantic_similarity_threshold
    self.per_page = settings.results_per_page
    self.clarify_threshold = settings.search_clarify_threshold
    self.fuzzy_enabled = settings.enable_fuzzy_search
```

(Removes: `trigram_threshold`, `trigram_title_w`, `fts_floor`.)

**Step 4.2: Rewrite `fts_search_fuzzy`**

Replace the entire method (lines 116-207) with:

```python
async def fts_search_fuzzy(
    self, session: AsyncSession, query: str, page: int = 1
) -> tuple[list[LessonResult], int]:
    """Score rows by sum of IDF weights of matching tokens.

    Candidate set: rows whose search_vector matches any token (OR-tsquery).
    Score per row: Σ idf_i * (search_vector @@ tok_i). Rare-token matches
    dominate — 'ньютон' outweighs 'закон' so 'Второй закон Ньютона' beats
    'Закон больших чисел' on the query '2 закон ньютона'.

    No prefix matching (Snowball stemmer handles morphology).
    No trigram fallback (removed 2026-04-14 after baseline showed it
    added noise for multi-word queries).
    """
    from sqlalchemy import text

    tokens = _normalize_tokens(query)
    if not tokens:
        return [], 0

    or_ts = _build_or_tsquery_string(tokens)
    weights = await _compute_idf(session, tokens)

    params: dict = {"or_ts": or_ts}
    score_parts: list[str] = []
    for i, tok in enumerate(tokens):
        key_tok = f"tok{i}"
        key_w = f"w{i}"
        params[key_tok] = tok
        params[key_w] = float(weights.get(tok, 1.0))
        score_parts.append(
            f"(CASE WHEN l.search_vector @@ to_tsquery('russian', cast(:{key_tok} as text)) "
            f"THEN cast(:{key_w} as float) ELSE 0 END)"
        )
    score_expr = " + ".join(score_parts) if score_parts else "0"

    sql = text(f"""
        SELECT l.id, ({score_expr}) AS score
        FROM lessons l
        WHERE l.search_vector @@ to_tsquery('russian', cast(:or_ts as text))
        ORDER BY (CASE WHEN l.url = 'N/A' THEN 1 ELSE 0 END),
                 score DESC,
                 l.id
    """)

    rows = (await session.execute(sql, params)).all()
    total = len(rows)

    offset = (page - 1) * self.per_page
    page_ids = [r.id for r in rows[offset: offset + self.per_page]]
    if not page_ids:
        return [], total

    q = (
        select(Lesson)
        .options(joinedload(Lesson.subject))
        .where(Lesson.id.in_(page_ids))
    )
    result = await session.execute(q)
    by_id = {l.id: l for l in result.scalars().unique().all()}

    lessons = [
        LessonResult(
            title=by_id[i].title, url=by_id[i].url,
            description=by_id[i].description,
            subject=by_id[i].subject.name,
            grade=by_id[i].grade,
            section=by_id[i].section,
            topic=by_id[i].topic,
            is_semantic=False,
        )
        for i in page_ids if i in by_id
    ]
    return lessons, total
```

**Step 4.3: Update the module docstring**

Replace lines 1-12 of `src/core/services/search.py` (the module docstring) with:

```python
"""Lesson search service.

Level 1 (lexical) routes through ``fts_search_fuzzy`` when
``settings.enable_fuzzy_search`` is True: an OR-tsquery on
``search_vector``, ranked by the sum of per-token IDF weights. When
the flag is False, the strict AND ``plainto_tsquery`` path
(``fts_search``) is used — kept as a rollback. Level 2 (lexical +
semantic embeddings) is unaffected.

See ``docs/plans/2026-04-14-search-quality-design.md`` for rationale.
"""
```

**Step 4.4: Run the whole test suite**

Run: `pytest tests/ -v`
Expected: all existing tests in `test_search.py` and `test_search_normalize.py` pass. `tests/test_config_fuzzy.py` may fail — handled in Task 5.

If anything unexpected fails, STOP and re-plan.

**Step 4.5: Commit**

```bash
git add src/core/services/search.py
git commit -m "$(cat <<'EOF'
feat(search): rank fuzzy L1 by sum of IDF-weighted token matches

Replace the three-CTE OR-FTS + pg_trgm pipeline with a single query
that scores rows by Σ idf_i * (search_vector @@ tok_i). Rare tokens
outweigh common ones, so 'ньютон' in '2 закон ньютона' pulls 'Второй
закон Ньютона' above 'Закон больших чисел'.

Drops:
- pg_trgm similarity leg (noise on multi-word queries, low ceiling
  on single-token recall improvements)
- prefix :* builder (handled earlier; this commit is the consumer)
- SearchService.trigram_threshold / trigram_title_w / fts_floor

Keeps the ENABLE_FUZZY_SEARCH rollback lane intact.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Delete dead settings from config

**Files:**
- Modify: `src/config.py:24-26` — remove three fields.
- Modify: `tests/test_config_fuzzy.py` — either delete if whole file covers removed settings, or trim.
- Modify: `tests/test_search.py:16-18` — drop the three removed mock attributes.
- Modify: `.env.example` — if the fields are mentioned, remove lines.

**Step 5.1: Inspect `tests/test_config_fuzzy.py`**

Run: `cat tests/test_config_fuzzy.py` (check what it tests).

- If every test targets one of the removed settings → delete the file.
- If it mixes `enable_fuzzy_search` (kept) with the removed ones → trim only the dead tests.

**Step 5.2: Remove settings from `src/config.py`**

Delete lines 24-26 (`trigram_similarity_threshold`, `trigram_title_weight`, `fts_score_floor`). `enable_fuzzy_search` on line 23 **stays**.

**Step 5.3: Trim `tests/test_search.py` fixture**

In `_make_mock_settings` (lines 8-19), delete these three lines:

```python
    settings.trigram_similarity_threshold = 0.3
    settings.trigram_title_weight = 1.0
    settings.fts_score_floor = 0.5
```

**Step 5.4: Check `.env` and `.env.example` for lingering refs**

Run: `grep -E "TRIGRAM|FTS_SCORE_FLOOR" .env .env.example`
If found, remove those lines (keep `ENABLE_FUZZY_SEARCH`).

**Step 5.5: Run the whole test suite**

Run: `pytest tests/ -v`
Expected: everything passes.

**Step 5.6: Commit**

```bash
git add src/config.py tests/test_search.py tests/test_config_fuzzy.py .env .env.example
git commit -m "$(cat <<'EOF'
chore(config): drop trigram + fts_score_floor settings

No longer consumed after the IDF-weighted fuzzy rewrite. Leaves
ENABLE_FUZZY_SEARCH in place as the rollback switch.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Rerun baseline, verify quality improved

No test changes — this is a manual-ish verification against the dev DB.

**Files:**
- Modify: `tasks/soft-search-baseline.md` — overwrite with new numbers.

**Step 6.1: Rerun the baseline script**

Run: `PYTHONIOENCODING=utf-8 python -m scripts.search_baseline 2>&1 | grep -v "asyncio\|proactor\|sslproto\|RuntimeError\|Traceback\|File \|AttributeError\|Exception ignored\|Fatal error\|protocol:\|transport:" | tee /dev/tty | tail -200`

**Step 6.2: Manually verify the three showcase queries**

Expected signals (exact ranking may vary by DB state):

- `2 закон ньютона` → `Масса. Сила. Второй и третий законы Ньютона` appears in **top 3** (was #4).
- `лабораторные по физике` → top 3 contains **no** row with `физико-химический` in the title (was #1, #2).
- `петр 1` → top 3 contains at least one row whose title mentions `Петр` or `Пётр` literally (was "Российская империя ..." which doesn't).

If any expected signal fails, STOP. Capture the actual top-5 in a comment and re-plan.

**Step 6.3: Diff latency**

Compare `L1 median ms` column in the new `tasks/soft-search-baseline.md` against the old one (`git show HEAD~5:tasks/soft-search-baseline.md` — count back to the design commit). Acceptable: same order of magnitude (~500–800 ms). If any query > 2× slower, STOP and investigate — likely means the per-token `count(*)` is expensive without the GIN helping, and we'd need to batch IDF lookups.

**Step 6.4: Commit the new baseline**

```bash
git add tasks/soft-search-baseline.md
git commit -m "$(cat <<'EOF'
docs(search): update baseline after IDF rewrite

Rerun of the 9 golden queries against the same dev DB. Compare against
the pre-change baseline in HEAD~N to see the quality delta on the three
showcase queries (2 закон ньютона, лабораторные по физике, петр 1).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Final check

**Step 7.1: Confirm git log is clean**

Run: `git log --oneline -10`
Expected: 6 new commits on top of `7f84a52` (design), no stray work-in-progress commits.

**Step 7.2: Run the full test suite one last time**

Run: `pytest tests/ -v`
Expected: all green.

**Step 7.3: Notify user**

Report:
- Commits on the branch (hashes + subjects)
- The three showcase quality deltas (from Task 6 output)
- Any latency changes worth flagging

---

## Notes for the executor

- **No database migration.** The schema `search_vector` column is unchanged; we're only changing how we query it.
- **If `tests/test_config_fuzzy.py` still references `trigram_*` fields after Task 5**, the test mock of `Settings` will break because the real `Settings` class no longer has those fields. Delete or trim accordingly.
- **Keep `ENABLE_FUZZY_SEARCH=true`** as the effective default — the new path is the one we want in prod.
- **Per-token IDF cost:** if profiling later shows it matters, the cheapest cache is a module-level dict keyed by token that TTLs every N minutes. Not in scope now.
- **The abbreviation filter** (`_abbr_filters`) still runs in the strict `fts_search` path but **not** in `fts_search_fuzzy`. That's intentional for this task (matches previous behavior) — if ВПР / ОГЭ / ЕГЭ ranking regresses, it's a separate fix.
