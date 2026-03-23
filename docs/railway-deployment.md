# Деплой проекта AITSOK на Railway

## Архитектура на Railway

Проект разворачивается как **2 сервиса** в одном Railway-проекте. База данных остаётся на **Supabase**.

| Сервис | Назначение | Команда запуска |
|--------|-----------|-----------------|
| **web** | FastAPI веб-приложение (регистрация) | `./start_web.sh` |
| **worker** | Telegram + MAX боты | `./start_worker.sh` |

База данных: **Supabase PostgreSQL** (pgvector включён через Supabase Dashboard).

---

## Шаг 1. Подготовка репозитория

### 1.1. Закоммить все файлы

```bash
git add Dockerfile start_web.sh start_worker.sh
git commit -m "chore: add deployment scripts"
git push origin main
```

### 1.2. Проверь окончания строк в .sh файлах (LF, не CRLF)

Railway запускает контейнеры на Linux. Если скрипты имеют CRLF — будет ошибка `/bin/bash^M: bad interpreter`.

```bash
# Проверить:
file start_web.sh start_worker.sh

# Если показывает "CRLF" — исправить:
sed -i 's/\r$//' start_web.sh start_worker.sh
```

Либо добавь в `.gitattributes`:

```
*.sh text eol=lf
```

---

## Шаг 2. Создание проекта на Railway

1. Зайди на [railway.app](https://railway.app) и войди через GitHub
2. Нажми **"New Project"**
3. Выбери **"Deploy from GitHub repo"**
4. Подключи репозиторий `bot_aitsok`

Railway автоматически создаст первый сервис. Мы настроим его как **worker** и добавим **web**.

---

## Шаг 3. Создание сервисов

### 3.1. Сервис Worker (боты)

Первый сервис, созданный при импорте репо — настрой его:

1. Кликни на сервис → **Settings**
2. **Service Name**: `worker`
3. **Build**: оставь Dockerfile (Railway сам определит)
4. **Deploy** → **Custom Start Command**:
   ```
   ./start_worker.sh
   ```
   *(или оставь пустым — Dockerfile по умолчанию запускает `start_worker.sh`)*

### 3.2. Сервис Web (веб-приложение)

1. В проекте нажми **"+ New"** → **"GitHub Repo"** → выбери тот же репозиторий
2. **Settings**:
   - **Service Name**: `web`
   - **Custom Start Command**:
     ```
     ./start_web.sh
     ```
3. **Networking**:
   - Нажми **"Generate Domain"** — Railway выдаст URL вида `web-production-xxxx.up.railway.app`
   - Или подключи свой домен

> **Важно**: Railway автоматически устанавливает переменную `PORT`. Наш `start_web.sh` уже использует `${PORT:-8000}` — всё корректно.

---

## Шаг 4. Настройка переменных окружения

### 4.1. Переменные для обоих сервисов

Задай переменные для **каждого сервиса** (worker и web). Чтобы не дублировать — используй **Shared Variables** в настройках проекта.

Кликни на сервис → **Variables** → **"+ New Variable"**:

| Переменная | Значение | Примечание |
|-----------|---------|------------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:port/db` | Supabase connection string с `+asyncpg` |
| `BOT_TOKEN` | `токен-telegram-бота` | От @BotFather |
| `MAX_BOT_TOKEN` | `токен-max-бота` | Токен MAX платформы |
| `ADMIN_IDS` | `123456789,987654321` | Telegram ID администраторов |
| `GOOGLE_SHEETS_LESSONS_ID` | `id-таблицы` | ID Google-таблицы с уроками |
| `GOOGLE_SHEETS_SCHOOLS_ID` | `id-таблицы` | ID Google-таблицы со школами |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | `{"type":"service_account",...}` | JSON сервисного аккаунта целиком |
| `OPENAI_API_KEY` | `sk-...` | Ключ OpenAI API |
| `ENABLE_TELEGRAM` | `true` | Включить Telegram-бота |
| `ENABLE_MAX` | `true` | Включить MAX-бота |
| `WEB_APP_URL` | `https://web-production-xxxx.up.railway.app` | URL веб-сервиса (из Шага 3.2) |

Опциональные:

| Переменная | По умолчанию | Примечание |
|-----------|-------------|------------|
| `FTS_MIN_RESULTS` | `3` | Мин. результатов полнотекстового поиска |
| `SEMANTIC_SIMILARITY_THRESHOLD` | `0.75` | Порог семантической близости |
| `RESULTS_PER_PAGE` | `5` | Результатов на страницу |

### 4.2. Shared Variables (рекомендуется)

Чтобы не вводить переменные дважды:

1. В проекте нажми **Settings** → **Shared Variables**
2. Добавь все переменные из таблицы выше
3. В каждом сервисе подключи shared-переменные

---

## Шаг 5. Деплой

### 5.1. Автоматический деплой

После настройки переменных Railway автоматически задеплоит оба сервиса. Каждый пуш в `main` тригерит редеплой.

### 5.2. Проверка логов

Кликни на сервис → **Deployments** → последний деплой:

- **worker**: `Running database migrations...` → `Starting bots...`
- **web**: `Running database migrations...` → `Starting web server...`

### 5.3. Проверка работоспособности

- **Web**: открой URL Railway в браузере — страница регистрации
- **Telegram-бот**: напиши `/start` боту
- **MAX-бот**: напиши `/start` боту

---

## Возможные проблемы и решения

### `^M: bad interpreter`
Windows-окончания строк (CRLF) в `.sh` файлах. Конвертируй в LF (см. Шаг 1.2).

### `could not translate host name` / `connection refused`
Supabase может блокировать подключения не из разрешённых сетей. В Supabase Dashboard → **Database** → **Network** убедись, что доступ открыт (или добавь `0.0.0.0/0` для Railway).

### Миграции падают с ошибкой pgvector
В Supabase Dashboard → **Database** → **Extensions** — включи расширение `vector`.

### Web-сервис не отвечает
Railway устанавливает `PORT`. Наш `start_web.sh` использует `${PORT:-8000}` — это корректно. Проверь, что домен сгенерирован (Шаг 3.2).

### `GOOGLE_SERVICE_ACCOUNT_JSON` не парсится
Вставь JSON одной строкой, без переносов. Railway корректно сохраняет такие значения.

### Оба сервиса запускают миграции одновременно
Это безопасно — Alembic использует advisory lock. Параллельные миграции не конфликтуют.

---

## Стоимость

- **Hobby Plan**: $5/мес (включает $5 кредитов)
- **Pro Plan**: $20/мес (включает $10 кредитов)
- Worker и Web — каждый потребляет ресурсы отдельно
- БД на Supabase — отдельный бесплатный/платный план

Для бота с небольшой нагрузкой Hobby Plan обычно достаточно.

---

## Итоговая структура

```
Railway Project: aitsok
├── worker (service)
│   ├── Source: GitHub repo
│   ├── Dockerfile: ./Dockerfile
│   ├── Start: ./start_worker.sh
│   └── Processes: Telegram bot + MAX bot
└── web (service)
    ├── Source: GitHub repo (тот же)
    ├── Dockerfile: ./Dockerfile
    ├── Start: ./start_web.sh
    ├── Port: $PORT (auto)
    └── Domain: *.up.railway.app

External:
└── Supabase PostgreSQL (pgvector)
```
