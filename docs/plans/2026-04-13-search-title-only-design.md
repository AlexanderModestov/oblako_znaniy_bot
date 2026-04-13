# Search: FTS по title-only

**Дата:** 2026-04-13
**Ветка:** dev_2_levels

## Цель

Сузить FTS-поиск (уровень 1) до одного поля — `Lesson.title`. Убрать из `search_vector` поля `description`, `section`, `topic`.

## Мотивация

Текущее поведение: `search_vector` склеивает title(A) + description(B) + section(C) + topic(C). Запросы матчатся по всем четырём полям, что даёт шум — уроки попадают в выдачу из-за случайного совпадения в описании.

Желаемое: находить урок только если слово(а) запроса есть в названии. Семантический уровень 2 компенсирует потерю recall для запросов, где название сформулировано иначе.

## Изменения

### 1. Схема / триггер

Новая миграция **`008_search_vector_title_only.py`**:

```sql
CREATE OR REPLACE FUNCTION lessons_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('russian', coalesce(NEW.title, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

- DROP старого триггера/функции (версия 007)
- CREATE нового (только title, без setweight)
- Backfill: `UPDATE lessons SET search_vector = to_tsvector('russian', coalesce(title, ''))`
- `downgrade()` — восстановление логики 007 (title/A + description/B + section/C + topic/C)

GIN-индекс по `search_vector` не пересоздаётся — работает с любым tsvector.

### 2. Код (`src/core/services/search.py`)

**`_abbr_filters`** — сузить фильтр по аббревиатурам до title:
```python
conditions.append(Lesson.title.ilike(pat))
```
(вместо `or_(title, description, section, topic)`)

**`fts_search` / `fts_search_all`** — без изменений. `ts_rank` продолжает ранжировать осмысленно (по частоте/позиции), хотя веса A/B/C больше не различают поля.

**`semantic_search`** — без изменений. Эмбеддинги уроков остаются посчитанными по полному контенту — это сознательное решение: семантика должна компенсировать сужение FTS.

**`check_clarification`** — без изменений.

### 3. Тесты

- Обновить `tests/test_models.py` (ассерты про содержимое `search_vector`)
- Добавить кейсы:
  1. Слово только в title → уровень 1 находит
  2. Слово только в description → уровень 1 пусто, уровень 2 подтягивает семантикой
  3. Аббревиатура (ОГЭ/ЕГЭ) — только уроки с ней в title

### 4. Порядок применения

1. `alembic upgrade head` — миграция 008 (атомарно: триггер + backfill)
2. Деплой кода с упрощённым `_abbr_filters`
3. Ручной smoke-test типичных запросов

### 5. Откат

- `alembic downgrade -1` — возврат к весам A/B/C и 4 полям
- `git revert` коммита с изменениями кода

## Нерешённые вопросы (вне текущего скоупа)

- Перегенерация эмбеддингов только по title (требует прогонки через OpenAI API)
- Тюнинг `clarify_threshold` после замера новой частоты срабатывания уточнений
