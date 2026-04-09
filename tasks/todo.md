# Ограничение поиска двумя уровнями

**Goal:** Убрать 3‑й уровень поиска (FTS OR‑логика), оставить только Level 1 (FTS AND) и Level 2 (FTS AND + семантика). Когда Level 2 не даёт результатов — показывать пользователю единственную кнопку «Новый поиск».

**Architecture:**
- В сервисе (`src/core/services/search.py`): убрать ветку `level >= 3` из `_build_level_results`, удалить неиспользуемый `_build_tsquery_or` и параметр `use_or` у `fts_search`/`fts_search_all`. Ужесточить валидацию уровня в `search_by_level`.
- В обоих handler'ах (Telegram + MAX): клампить уровень до `2`, убрать текстовую метку «Максимальный поиск», упростить построение клавиатуры для пустого результата.
- В обеих клавиатурах (`src/telegram/keyboards.py`, `src/max/keyboards.py`): сменить условие показа кнопки «Расширить поиск» с `level < 3` на `level < 2`.
- Тесты: удалить тесты под OR‑ветку, добавить тест на то, что Level 2 не вызывает OR‑FTS, обновить тест валидации.

**Tech Stack:** Python 3.11+, SQLAlchemy async, aiogram (Telegram), maxapi (MAX), pytest‑asyncio.

**Assumed behavior after change:**
- На Level 1 с 0 результатов → кнопки «Расширить поиск» + «Новый поиск» (без изменений).
- На Level 2 с N > 0 результатов → пагинация + «Новый поиск» (без «Расширить»).
- **На Level 2 с 0 результатов → только «Новый поиск»** (главная цель задачи).
- Кнопка «Расширить» при Level 1 → эскалирует до Level 2.
- Любой вызов `search_by_level(level=3)` из старых callback'ов (застарелые сообщения) → `ValueError` в сервисе; handler clamps до 2 раньше, так что до сервиса не дойдёт.

---

## Task 1: Почистить сервис поиска от Level 3 / OR‑логики

**Files:**
- Modify: `src/core/services/search.py:23-28` (удалить `_build_tsquery_or`)
- Modify: `src/core/services/search.py:54` (убрать параметр `use_or` у `fts_search`)
- Modify: `src/core/services/search.py:55` (убрать ветку `_build_tsquery_or`)
- Modify: `src/core/services/search.py:130-149` (убрать блок `if level >= 3`)
- Modify: `src/core/services/search.py:151-168` (валидация `level in (1, 2)`)
- Modify: `src/core/services/search.py:226` (убрать параметр `use_or` у `fts_search_all`)
- Modify: `src/core/services/search.py:228` (убрать ветку `_build_tsquery_or`)

**Step 1.1: Удалить `_build_tsquery_or`**

Удалить строки 23–28:
```python
def _build_tsquery_or(query: str):
    """OR logic: any word matches. Used as fallback when AND yields too few results."""
    words = query.strip().split()
    if len(words) <= 1:
        return func.plainto_tsquery("russian", query)
    return func.websearch_to_tsquery("russian", " OR ".join(words))
```

**Step 1.2: Убрать `use_or` из сигнатуры и тела `fts_search`**

Было (строка 54):
```python
async def fts_search(self, session: AsyncSession, query: str, page: int = 1, use_or: bool = False) -> tuple[list[LessonResult], int]:
    ts_query = _build_tsquery_or(query) if use_or else _build_tsquery(query)
```

Стало:
```python
async def fts_search(self, session: AsyncSession, query: str, page: int = 1) -> tuple[list[LessonResult], int]:
    ts_query = _build_tsquery(query)
```

**Step 1.3: Убрать `use_or` из сигнатуры и тела `fts_search_all`**

Было (строка 226):
```python
async def fts_search_all(self, session: AsyncSession, query: str, use_or: bool = False) -> list[LessonResult]:
    """Fetch all FTS results without pagination (for clarification analysis)."""
    ts_query = _build_tsquery_or(query) if use_or else _build_tsquery(query)
```

Стало:
```python
async def fts_search_all(self, session: AsyncSession, query: str) -> list[LessonResult]:
    """Fetch all FTS results without pagination (for clarification analysis)."""
    ts_query = _build_tsquery(query)
```

**Step 1.4: Убрать блок `if level >= 3` из `_build_level_results`**

Было (строки 144–147):
```python
if level >= 3:
    seen_urls = {l.url for l in combined}
    or_lessons = await self.fts_search_all(session, query, use_or=True)
    combined += [l for l in or_lessons if l.url not in seen_urls]

return combined
```

Стало:
```python
return combined
```

Также проверить, что docstring метода `_build_level_results` не упоминает level 3: изменить строку 131 с `"""Build accumulated lesson list for level 2 or 3 (no pagination)."""` на `"""Build accumulated lesson list for level 2 (no pagination)."""`.

**Step 1.5: Ужесточить валидацию в `search_by_level`**

Было (строки 153–154):
```python
if level not in (1, 2, 3):
    raise ValueError(f"Invalid search level: {level!r}. Must be 1, 2, or 3.")
```

Стало:
```python
if level not in (1, 2):
    raise ValueError(f"Invalid search level: {level!r}. Must be 1 or 2.")
```

Обновить docstring (строка 152): `"""Search at the given level (1=AND, 2=AND+semantic), paginated."""`.

**Step 1.6: Запустить тесты сервиса — ожидаемо 3 упадут**

Run: `pytest tests/test_search.py -v`
Expected failures:
- `test_build_tsquery_or_multiple_words` — ImportError на `_build_tsquery_or`
- `test_build_tsquery_or_single_word` — ImportError
- `test_search_by_level_3_adds_or_results` — level=3 теперь ValueError
- `test_search_by_level_invalid_raises` — тестирует level=0, должен продолжить работать

Если падают другие тесты — СТОП, разбираться.

---

## Task 2: Обновить тесты сервиса

**Files:**
- Modify: `tests/test_search.py:49-63` (удалить OR‑тесты)
- Modify: `tests/test_search.py:214-233` (заменить level‑3 тест на level‑2‑без‑OR)
- Modify: `tests/test_search.py:236-241` (обновить invalid‑raises: добавить level=3)

**Step 2.1: Удалить тесты `_build_tsquery_or`**

Удалить строки 49–63:
```python
def test_build_tsquery_or_multiple_words():
    from src.core.services.search import _build_tsquery_or
    expr = _build_tsquery_or("тангенс котангенс")
    ...

def test_build_tsquery_or_single_word():
    from src.core.services.search import _build_tsquery_or
    expr = _build_tsquery_or("тангенс")
    ...
```

**Step 2.2: Заменить `test_search_by_level_3_adds_or_results` на `test_search_by_level_2_does_not_call_or_fts`**

Заменить строки 214–233:
```python
@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_search_by_level_2_does_not_call_or_fts(mock_settings):
    """Level 2 must NOT invoke OR-FTS (that was level 3, now removed)."""
    service = SearchService()
    and_lesson = _make_lesson(subject="История")
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    with patch.object(service, "fts_search_all", new_callable=AsyncMock) as mock_all, \
         patch.object(service, "semantic_search", new_callable=AsyncMock) as mock_sem:
        mock_all.return_value = [and_lesson]
        mock_sem.return_value = []
        result = await service.search_by_level(mock_session, "история", level=2)
    assert result.total == 1
    # Critical: fts_search_all should be called exactly ONCE (AND only, no OR pass).
    assert mock_all.call_count == 1
    # And never with use_or=True (parameter removed, but double-check via kwargs).
    for call in mock_all.call_args_list:
        assert "use_or" not in call.kwargs
```

**Step 2.3: Расширить `test_search_by_level_invalid_raises`**

Заменить строки 236–241:
```python
@pytest.mark.asyncio
@patch("src.core.services.search.get_settings", side_effect=_make_mock_settings)
async def test_search_by_level_invalid_raises(mock_settings):
    service = SearchService()
    with pytest.raises(ValueError, match="Invalid search level"):
        await service.search_by_level(MagicMock(), "история", level=0)
    with pytest.raises(ValueError, match="Invalid search level"):
        await service.search_by_level(MagicMock(), "история", level=3)
```

**Step 2.4: Прогнать тесты сервиса — всё должно пройти**

Run: `pytest tests/test_search.py -v`
Expected: PASS всё (включая новый `test_search_by_level_2_does_not_call_or_fts`).

**Step 2.5: Commit**

```bash
git add src/core/services/search.py tests/test_search.py
git commit -m "$(cat <<'EOF'
refactor(search): remove level 3 (OR-FTS) from search service

Drop the OR-FTS fallback branch from _build_level_results and clean up
dead code (_build_tsquery_or, use_or parameter). search_by_level now
only accepts levels 1 and 2. Tests updated to verify level 2 never
invokes OR-FTS.
EOF
)"
```

---

## Task 3: Обновить клавиатуры (оба канала)

**Files:**
- Modify: `src/telegram/keyboards.py:119` (сменить `level < 3` → `level < 2`)
- Modify: `src/max/keyboards.py:105` (то же)

**Step 3.1: Telegram keyboard**

Было (строка 119):
```python
if level < 3:
    buttons.append([
        InlineKeyboardButton(text="\U0001f50d Расширить поиск", callback_data="search:expand")
    ])
```

Стало:
```python
if level < 2:
    buttons.append([
        InlineKeyboardButton(text="\U0001f50d Расширить поиск", callback_data="search:expand")
    ])
```

**Step 3.2: MAX keyboard**

Было (строка 105):
```python
if level < 3:
    kb.row(CallbackButton(text="\U0001f50d Расширить поиск", payload="search:expand"))
```

Стало:
```python
if level < 2:
    kb.row(CallbackButton(text="\U0001f50d Расширить поиск", payload="search:expand"))
```

**Step 3.3: Проверить, что тесты всё ещё зелёные (клавиатуры без юнит-тестов, но сервис — тронут)**

Run: `pytest tests/ -v`
Expected: PASS всё.

---

## Task 4: Обновить Telegram handler

**Files:**
- Modify: `src/telegram/handlers/search.py:75` (clamp 3 → 2)
- Modify: `src/telegram/handlers/search.py:121-130` (убрать ветку level==3, упростить keyboard)
- Modify: `src/telegram/handlers/search.py:179-189` (то же в `handle_clarify_back`)

**Step 4.1: Изменить clamp в `handle_expand`**

Было (строка 75):
```python
new_level = min(current_level + 1, 3)
```

Стало:
```python
new_level = min(current_level + 1, 2)
```

**Step 4.2: Упростить построение keyboard в `_run_search`**

Было (строки 121–130):
```python
text = format_text_results(result)
if level == 2:
    text += "\n\n\U0001f50e Расширенный поиск (семантика)"
elif level == 3:
    text += "\n\n\U0001f50e Максимальный поиск"
if result.total_pages > 0:
    keyboard = search_pagination_keyboard(1, result.total_pages, level)
elif level < 3:
    keyboard = search_pagination_keyboard(1, 1, level)
else:
    keyboard = None
```

Стало:
```python
text = format_text_results(result)
if level == 2:
    text += "\n\n\U0001f50e Расширенный поиск (семантика)"
total_pages = max(result.total_pages, 1)
keyboard = search_pagination_keyboard(1, total_pages, level)
```

**Обоснование:** `search_pagination_keyboard` после изменений в Task 3 уже сама решает, показывать ли «Расширить» (только при `level < 2`). Для пустого результата всегда будет только «Новый поиск» при level=2 и «Расширить + Новый поиск» при level=1 — ровно то, что нужно.

**Step 4.3: То же упрощение в `handle_clarify_back`**

Было (строки 179–189):
```python
text = format_text_results(result)
if search_level == 2:
    text += "\n\n\U0001f50e Расширенный поиск (семантика)"
elif search_level == 3:
    text += "\n\n\U0001f50e Максимальный поиск"
if result.total_pages > 0:
    keyboard = search_pagination_keyboard(1, result.total_pages, search_level)
elif search_level < 3:
    keyboard = search_pagination_keyboard(1, 1, search_level)
else:
    keyboard = None
```

Стало:
```python
text = format_text_results(result)
if search_level == 2:
    text += "\n\n\U0001f50e Расширенный поиск (семантика)"
total_pages = max(result.total_pages, 1)
keyboard = search_pagination_keyboard(1, total_pages, search_level)
```

**Step 4.4: Проверить, что в файле больше нет упоминаний level 3**

Run: `grep -n "level.*3\|level == 3\|level >= 3" src/telegram/handlers/search.py`
Expected: пусто (или только безобидные вхождения, которых быть не должно).

---

## Task 5: Обновить MAX handler

**Files:**
- Modify: `src/max/handlers/search.py:68` (clamp 3 → 2)
- Modify: `src/max/handlers/search.py:106-116` (убрать level==3, упростить keyboard)
- Modify: `src/max/handlers/search.py:119-136` (упростить ветку if kb)
- Modify: `src/max/handlers/search.py:182-191` (то же в `handle_clarify_back`)
- Modify: `src/max/handlers/search.py:194-201` (то же)

**Step 5.1: Clamp в `handle_expand`**

Было (строка 68):
```python
new_level = min(current_level + 1, 3)
```

Стало:
```python
new_level = min(current_level + 1, 2)
```

Также подредактировать логи строк 64–69, чтобы убрать упоминания level 3 если есть.

**Step 5.2: Упростить keyboard в `_run_search`**

Было (строки 106–136):
```python
text = format_text_results(result)
if level == 2:
    text += "\n\n\U0001f50e Расширенный поиск (семантика)"
elif level == 3:
    text += "\n\n\U0001f50e Максимальный поиск"

if result.total_pages > 0:
    kb = search_pagination_keyboard(1, result.total_pages, level)
elif level < 3:
    kb = search_pagination_keyboard(1, 1, level)
else:
    kb = None

logger.info("_run_search: level=%d, total=%d, text_len=%d, edit=%s", level, total, len(text), edit)
if kb:
    if edit:
        try:
            await event.bot.edit_message(
                message_id=event.message.body.mid,
                text=text,
                attachments=[kb.as_markup()],
            )
            logger.info("_run_search: edit_message succeeded")
        except Exception:
            logger.exception("_run_search: edit_message failed")
    else:
        await event.message.answer(text, attachments=[kb.as_markup()])
else:
    if edit:
        await event.bot.edit_message(message_id=event.message.body.mid, text=text)
    else:
        await event.message.answer(text)
```

Стало:
```python
text = format_text_results(result)
if level == 2:
    text += "\n\n\U0001f50e Расширенный поиск (семантика)"

total_pages = max(result.total_pages, 1)
kb = search_pagination_keyboard(1, total_pages, level)

logger.info("_run_search: level=%d, total=%d, text_len=%d, edit=%s", level, total, len(text), edit)
if edit:
    try:
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text=text,
            attachments=[kb.as_markup()],
        )
        logger.info("_run_search: edit_message succeeded")
    except Exception:
        logger.exception("_run_search: edit_message failed")
else:
    await event.message.answer(text, attachments=[kb.as_markup()])
```

**Обоснование:** после упрощения `kb` всегда не‑None, поэтому ветка `else: edit_message без вложений` мертва и может быть удалена.

**Step 5.3: То же в `handle_clarify_back`**

Было (строки 182–201):
```python
text = format_text_results(result)
if search_level == 2:
    text += "\n\n\U0001f50e Расширенный поиск (семантика)"
elif search_level == 3:
    text += "\n\n\U0001f50e Максимальный поиск"
if result.total_pages > 0:
    kb = search_pagination_keyboard(1, result.total_pages, search_level)
elif search_level < 3:
    kb = search_pagination_keyboard(1, 1, search_level)
else:
    kb = None

await context.update_data(clarify_result=None, search_filtered=None)
if kb:
    await event.bot.edit_message(
        message_id=event.message.body.mid,
        text=text,
        attachments=[kb.as_markup()],
    )
else:
    await event.bot.edit_message(message_id=event.message.body.mid, text=text)
```

Стало:
```python
text = format_text_results(result)
if search_level == 2:
    text += "\n\n\U0001f50e Расширенный поиск (семантика)"

total_pages = max(result.total_pages, 1)
kb = search_pagination_keyboard(1, total_pages, search_level)

await context.update_data(clarify_result=None, search_filtered=None)
await event.bot.edit_message(
    message_id=event.message.body.mid,
    text=text,
    attachments=[kb.as_markup()],
)
```

**Step 5.4: Проверить, что level 3 нигде не остался**

Run: `grep -n "level.*3\|level == 3\|level >= 3\|Максимальный" src/max/handlers/search.py`
Expected: пусто.

**Step 5.5: Запустить полный набор тестов**

Run: `pytest tests/ -v`
Expected: PASS всё.

**Step 5.6: Commit**

```bash
git add src/telegram/keyboards.py src/max/keyboards.py src/telegram/handlers/search.py src/max/handlers/search.py
git commit -m "$(cat <<'EOF'
feat(search): cap max search level at 2, show 'New search' only when empty

- handle_expand clamps to level 2 instead of 3 (both Telegram and MAX)
- 'Расширить поиск' button hidden at level >= 2
- Empty level-2 results now show only 'Новый поиск' button
- Removed dead 'Максимальный поиск' label and kb=None branches

Motivation: level 3 (OR-FTS) generated too much noise for users.
Semantic search at level 2 already covers the recall gap cleanly.
EOF
)"
```

---

## Task 6: Ручная проверка на живом боте (опционально, но рекомендую)

**Проверить сценарии в Telegram И MAX:**

1. **Пустой Level 1:** запрос заведомо не существующим словом (напр. `xyzxyz`) → «ничего не найдено» + «Расширить поиск» + «Новый поиск». Жмём «Расширить» → Level 2.
2. **Пустой Level 2:** из предыдущего → снова «ничего не найдено» + **только** «Новый поиск». Жмём → возврат к меню поиска.
3. **Level 1 с результатами:** обычный запрос → список + пагинация + «Расширить поиск» + «Новый поиск». Жмём «Расширить» → переход на Level 2 (должно быть больше/другие результаты из семантики).
4. **Level 2 с результатами:** пагинация работает, кнопки «Расширить» НЕТ, «Новый поиск» есть.
5. **Level 2 с clarification:** если результатов > 10, показывается уточнение subject→grade→topic, кнопка «Назад» работает (не регресс).
6. **Старое сообщение с кнопкой «Расширить» на Level 2** (если сохранилось из прошлой сессии): жмём → `handle_expand` clamps до 2, `_run_search(level=2)` перерисует ту же страницу, `_safe_edit` гасит ошибку «message not modified» — должен отработать без краша.

---

## Review

### Что сделано
Все 5 задач реализации выполнены по плану, двумя коммитами на ветке `dev_2_levels`:

1. **`f0fa9c5 refactor(search): remove level 3 (OR-FTS) from search service`** — Task 1 + 2
   - Удалён `_build_tsquery_or` из `src/core/services/search.py`
   - Убран параметр `use_or` из `fts_search` и `fts_search_all`
   - Убран блок `if level >= 3` из `_build_level_results`
   - `search_by_level` теперь валидирует `level in (1, 2)` и raise'ит на всё остальное
   - Docstrings обновлены
   - Удалены 2 теста `_build_tsquery_or`
   - `test_search_by_level_3_adds_or_results` → `test_search_by_level_2_does_not_call_or_fts` (новый тест утверждает, что FTS-all вызывается ровно 1 раз и никогда с `use_or=True`)
   - `test_search_by_level_invalid_raises` расширен — проверяет и `level=0`, и `level=3`

2. **`0f221e4 feat(search): cap max search level at 2, show only 'New search' when empty`** — Task 3 + 4 + 5
   - `src/telegram/keyboards.py:119` и `src/max/keyboards.py:105`: `if level < 3` → `if level < 2`
   - Оба handler'а: `new_level = min(current_level + 1, 3)` → `min(..., 2)`
   - Оба handler'а: убраны ветки `elif level == 3` с меткой «Максимальный поиск»
   - Оба handler'а: упрощена логика клавиатуры для пустых результатов — `keyboard = search_pagination_keyboard(1, max(total_pages, 1), level)` вместо тройного `if/elif/else`
   - В MAX handler удалена мёртвая ветка `kb = None` и соответствующий `if kb` раунд
   - То же сделано в `handle_clarify_back` обоих handler'ов
   - Итог: −61 / +29 строк кода

**Проверка тестами:** 34/34 зелёных (исключая 2 предсуществующих фейла в `tests/test_models.py::test_subject_model` и `test_lesson_model_has_required_fields` — они про `Subject.code`, не связаны с этой задачей и присутствуют в ветке до моих изменений).

### Что пошло не по плану
Ничего. План выполнен линейно, без отступлений.

Замечания:
- Обнаружены 2 предсуществующих падения тестов в `test_models.py` (про `Subject.code`). Проверил через `git stash` — они падают и без моих изменений. Оставил как есть, это отдельная задача.
- Заметил, что работа уже велась на ветке `dev_2_levels` (видимо, кто-то/я заранее создал для этой фичи), так что дополнительного worktree не потребовалось.
- Проект на Windows, git показывает CRLF-предупреждения при коммитах handler'ов — это нормальное поведение core.autocrlf, не требует действий.

### Lessons
Корректировок от пользователя в процессе реализации не было — план был принят с первого раза. Новых правил для `tasks/lessons.md` нет.

Что стоит запомнить для аналогичных задач в будущем:
- **Упрощение keyboard-ветки через `max(total_pages, 1)`** — полезный приём, когда builder-функция сама умеет вырождаться под `total_pages=1`. Избавляет от дублирования и `kb=None`-ветки.
- **Порядок операций при удалении функционала:** сначала убрать код (тесты ожидаемо покраснеют), затем обновить тесты, затем прогон. Так видно, что именно удалённый код ломал, и не соблазняемся подогнать тест под код.
- **Проверка предсуществующих фейлов через `git stash`** — быстрый способ подтвердить, что свежее падение не от тебя, прежде чем паниковать.

### Следующие шаги (на твоё решение)
1. **Ручная проверка на живом боте** по 6 сценариям из Task 6 плана — тесты не покрывают UI‑слой.
2. **Мерж `dev_2_levels` → `main`** после валидации.
3. **Опционально:** если хочешь, могу отдельным коммитом починить предсуществующие падения `test_models.py` (похоже, там устарела проверка поля `Subject.code`).
