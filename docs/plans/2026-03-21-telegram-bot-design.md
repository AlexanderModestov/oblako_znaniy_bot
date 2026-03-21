# Telegram-бот для учителей: поиск учебного контента — Дизайн

Дата: 2026-03-21

## 1. Архитектура

```
Interfaces (Telegram, Max future)
        │
        ▼
   Core Engine
   ├── Onboarding Service
   ├── Search Engine (FTS + Semantic)
   ├── User Service
   ├── Content Service
   └── Admin Service
        │
        ▼
   Data Layer
   ├── PostgreSQL (Supabase) + pgvector
   ├── Google Sheets (source of truth)
   └── OpenAI API (embeddings)
```

Ключевой принцип: Core Engine не знает о мессенджерах. Адаптер переводит события мессенджера в вызовы сервисов ядра и форматирует ответы обратно. Добавить Max — написать новый адаптер без изменения ядра.

## 2. Стек

- **Python + aiogram 3** — Telegram-адаптер
- **SQLAlchemy 2.x + asyncpg** — ORM + async PostgreSQL
- **Alembic** — миграции БД
- **gspread + google-auth** — Google Sheets
- **openai** — эмбеддинги (text-embedding-3-small)
- **pydantic** — валидация и DTO
- **Docker** — деплой на Railway
- **PostgreSQL (Supabase)** — БД + pgvector

## 3. Структура базы данных

### users
| Столбец | Тип | Описание |
|---------|-----|----------|
| id | SERIAL PK | |
| telegram_id | BIGINT UNIQUE NULL | Nullable для будущего Max |
| full_name | VARCHAR(255) NOT NULL | Имя и фамилия |
| phone | VARCHAR(20) NOT NULL | Телефон |
| email | VARCHAR(255) NULL | Опционально |
| region_id | INT FK → regions.id | |
| school_id | INT FK → schools.id | |
| subjects | INT[] | Массив FK → subjects.id |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | |

### regions
| Столбец | Тип | Описание |
|---------|-----|----------|
| id | SERIAL PK | |
| name | VARCHAR(255) NOT NULL UNIQUE | |

### schools
| Столбец | Тип | Описание |
|---------|-----|----------|
| id | SERIAL PK | |
| region_id | INT FK → regions.id | |
| name | VARCHAR(255) NOT NULL | |
| | UNIQUE(region_id, name) | |

### subjects
| Столбец | Тип | Описание |
|---------|-----|----------|
| id | SERIAL PK | |
| name | VARCHAR(255) NOT NULL UNIQUE | |

### lessons
| Столбец | Тип | Описание |
|---------|-----|----------|
| id | SERIAL PK | |
| subject_id | INT FK → subjects.id | |
| grade | SMALLINT NOT NULL | 1-11 |
| section | VARCHAR(255) NULL | Раздел |
| topic | VARCHAR(255) NULL | Тема |
| title | VARCHAR(255) NOT NULL | Название урока |
| lesson_type | VARCHAR(50) NOT NULL | теория/практика/... |
| url | TEXT NOT NULL | Ссылка на Госуслуги |
| search_vector | TSVECTOR | Auto-generated для FTS |
| embedding | VECTOR(1536) | OpenAI embedding |
| created_at | TIMESTAMPTZ | |

### Индексы
- GIN на `search_vector` — полнотекстовый поиск
- IVFFlat или HNSW на `embedding` — векторный поиск
- B-tree на `(subject_id, grade)` — фильтрация Пути А

## 4. Онбординг (FSM)

Шаги при первом `/start`:

1. **Имя и фамилия** — свободный ввод, валидация: минимум 2 слова
2. **Регион** — пользователь печатает, бот отвечает кнопками-совпадениями (ILIKE, до 8 вариантов)
3. **Школа** — аналогично, фильтрация по выбранному региону
4. **Предметы** — inline-кнопки с toggle (✓/✗), кнопка "Готово"
5. **Телефон** — кнопка "Отправить контакт" или ручной ввод
6. **Email** — свободный ввод или "Пропустить"

На каждом шаге доступна кнопка "Назад". Повторный `/start` от зарегистрированного пользователя → главное меню.

## 5. Поиск — Путь А (по параметрам)

Последовательный выбор через кнопки:

1. **Предмет** — кнопки из subjects
2. **Класс** — отфильтрованные по предмету (DISTINCT grade)
3. **Раздел** — + "Пропустить" (DISTINCT section)
4. **Тема** — только если выбран раздел, + "Пропустить"
5. **Урок** — только если выбрана тема, + "Пропустить"

Кнопки генерируются динамически — только реально существующие комбинации. "Пропустить" выводит все уроки по текущим фильтрам.

Формат результата:
```
📚 Линейная функция
Вид: Теория
→ https://gosuslugi.ru/...
```

Пагинация: 5 результатов на страницу, кнопки "◀ Назад" / "Далее ▶". Кнопка "🔄 Новый поиск" под результатами.

## 6. Поиск — Путь Б (по ключевым словам, гибридный)

Стратегия: FTS-first, семантика как fallback.

1. Пользователь вводит текст
2. FTS-запрос: `plainto_tsquery('russian', запрос)` против `search_vector`
3. Если ≥ 3 результата → выводим FTS
4. Если < 3 → дополняем семантическим поиском:
   - Генерируем эмбеддинг запроса через OpenAI
   - Cosine similarity по `embedding` в lessons (порог > 0.75)
   - Объединяем с FTS, убираем дубли, FTS-результаты выше

Формат результата (расширенный):
```
🔎 По запросу «Никон» найдено 3 результата:

1. История | Раскол церкви
   📚 Патриарх Никон и его реформы
   Вид: Теория
   → https://gosuslugi.ru/...

3. 🤖 История | Церковь и государство
   📚 Религиозные реформы XVII века
   Вид: Теория
   → https://gosuslugi.ru/...
```

Результаты из семантического поиска помечены 🤖.

## 7. Загрузка данных (/reload)

Доступно только админам (список telegram_id в .env).

1. Скачивание Google Sheets (API v4, service account)
2. Валидация — логирование строк с ошибками
3. UPSERT справочников (subjects, regions, schools)
4. Полная перезапись lessons (DELETE + INSERT в транзакции)
5. Батчевая генерация эмбеддингов через OpenAI (до 2048 за раз)
6. search_vector генерируется триггером PostgreSQL

Стоимость эмбеддингов: ~$0.001 за 1200 уроков.

## 8. Обработка ошибок

**Пользовательские:**
- Ввод вместо кнопки → мягкое напоминание
- Нет результатов → предложение изменить запрос или способ поиска
- Случайное сообщение в FSM → повтор текущего шага
- Повторный /start → главное меню

**Технические:**
- Google Sheets недоступен → данные в БД не трогаем, сообщение админу
- OpenAI недоступен при поиске → fallback только на FTS
- OpenAI недоступен при /reload → уроки без эмбеддингов + предупреждение
- Supabase недоступен → "Сервис временно недоступен"
- Telegram rate limits → RetryMiddleware (aiogram)

**Безопасность:**
- Админ-команды по whitelist telegram_id
- Credentials в переменных окружения
- SQLAlchemy параметризованные запросы

## 9. Структура проекта

```
bot_aitsok/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── alembic/
│   └── versions/
├── alembic.ini
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── database.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── search.py
│   │   │   ├── content.py
│   │   │   └── loader.py
│   │   └── schemas.py
│   ├── telegram/
│   │   ├── __init__.py
│   │   ├── bot.py
│   │   ├── middlewares.py
│   │   ├── keyboards.py
│   │   ├── formatters.py
│   │   └── handlers/
│   │       ├── __init__.py
│   │       ├── start.py
│   │       ├── menu.py
│   │       ├── param_search.py
│   │       ├── text_search.py
│   │       └── admin.py
│   └── max/
│       └── __init__.py
└── tests/
    ├── test_search.py
    ├── test_loader.py
    └── test_onboarding.py
```

## 10. Замечания к исходному ТЗ

1. **"Excel/CSV"** → источник данных — Google Sheets
2. **"Столбец H"** → привязываться к названию столбца, не к букве
3. **"Maks"** → Max (мессенджер). ТЗ должно отражать мультиплатформенную архитектуру
4. **Телефон из Max** → в MVP через Telegram contact sharing
5. **Нет пагинации** → 5 результатов на страницу с навигацией
6. **Нет поведения при пустом результате** → добавлено
7. **Нет админ-функций** → /reload + /stats
8. **Тип поиска не указан** → FTS + семантический с fallback
9. **Нет эмбеддингов в ТЗ** → OpenAI text-embedding-3-small
