# MAX Messenger Bot — Design

## Overview

Третий интерфейс к поисковому ядру AITSOK — бот для мессенджера MAX. Логика онбординга и поиска полностью совпадает с Telegram-ботом. Web App (Mini App) для регистрации переиспользуется.

## Решения

- **SDK:** `maxapi` (pip install maxapi) — async, архитектура аналогична aiogram (Bot, Dispatcher, декораторы)
- **Структура кода:** отдельная директория `src/max/`, зеркальная `src/telegram/`, общие сервисы из `src/core/`
- **Запуск:** один процесс, `asyncio.gather`, флаги `ENABLE_TELEGRAM` / `ENABLE_MAX`
- **Polling:** long polling для обоих ботов
- **Web App:** тот же FastAPI-сервер и HTML-форма, валидация auth адаптирована под MAX
- **Пользователи:** регистрация через Telegram и MAX создаёт отдельных пользователей

## Структура файлов

### Новые файлы

```
src/max/
├── __init__.py
├── bot.py              # Bot + Dispatcher (maxapi)
├── formatters.py       # Форматирование сообщений
├── keyboards.py        # Inline-кнопки (maxapi.types)
└── handlers/
    ├── __init__.py
    ├── start.py        # /start, онбординг
    ├── menu.py         # Навигация по меню
    ├── text_search.py  # Текстовый поиск
    ├── param_search.py # Поиск по параметрам
    └── admin.py        # Админ-команды
```

### Изменения в существующих файлах

| Файл | Изменение |
|------|-----------|
| `src/config.py` | `MAX_BOT_TOKEN`, `ENABLE_MAX`, `ENABLE_TELEGRAM` |
| `src/core/models.py` | `max_user_id` (BigInteger, unique, nullable); `telegram_id` становится nullable |
| `src/web/auth.py` | Добавить `validate_max_webapp()` |
| `src/web/routes.py` | Параметр `platform` для выбора валидации |
| `main.py` | Условный запуск обоих ботов через `asyncio.gather` |
| `.env` | `MAX_BOT_TOKEN`, `ENABLE_MAX`, `ENABLE_TELEGRAM` |
| `requirements.txt` | `maxapi` |

### Миграция Alembic

- Добавить колонку `max_user_id` (BigInteger, unique, nullable)
- Сделать `telegram_id` nullable

## Маппинг концепций aiogram → maxapi

| Концепция | aiogram (Telegram) | maxapi (MAX) |
|---|---|---|
| Старт бота | `Message` с текстом `/start` | `BotStarted` event |
| Сообщение | `Message` | `MessageCreated` |
| Callback | `CallbackQuery` | `MessageCallback` |
| Ответ | `message.answer()` | `event.message.answer()` |
| Клавиатуры | `InlineKeyboardMarkup` | аналог из `maxapi.types` |

## Конфигурация и запуск

```python
# main.py
tasks = []
if settings.ENABLE_TELEGRAM:
    tasks.append(start_telegram_polling())
if settings.ENABLE_MAX:
    tasks.append(start_max_polling())
tasks.append(start_web_server())
await asyncio.gather(*tasks)
```

## Обработка ошибок

- Каждый бот оборачивает polling в `try/except`, логирует ошибки, не роняет другой бот
- Логгер с префиксом: `logging.getLogger("max")`
- Админ-команда `/reload` вызывает общий `loader.reload_data()`

## Ограничения MAX API

- Нет inline-режима (`@bot query`)
- Нет Payments API
- Для публикации нужно юрлицо РФ + модерация ~48ч
- Rate limit: 30 rps
- Кнопки: макс 210 штук, 30 рядов, 7 в ряду
