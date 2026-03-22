# Telegram Web App — Дизайн

## Цель

Создать веб-интерфейс регистрации (Telegram Mini App), аналогичный онбордингу в Telegram-боте.
Открывается через MenuButton внутри чата с ботом.

## Архитектура

```
src/
├── core/          # без изменений — переиспользуем UserService, модели, схемы
├── telegram/      # добавим установку MenuButton при старте бота
└── web/           # НОВАЯ папка
    ├── app.py     # FastAPI, lifespan, статика
    ├── routes.py  # API эндпоинты
    ├── auth.py    # Валидация Telegram initData (HMAC-SHA256)
    └── static/
        ├── index.html
        ├── style.css
        └── app.js
```

- FastAPI подключается к той же БД через `get_async_session()`
- Web-сервер запускается отдельно от бота
- initData валидируется на каждый запрос через FastAPI dependency
- Фронтенд использует `Telegram.WebApp.themeParams`

## API эндпоинты

```
POST /api/auth          — валидация initData, возврат telegram_id + статус (new/existing)
GET  /api/regions       — список регионов (?q= для поиска)
GET  /api/schools/:id   — школы по region_id (?q= для поиска)
GET  /api/subjects      — список предметов
POST /api/register      — сохранение пользователя
```

### Поток регистрации

1. Web App → JS отправляет `Telegram.WebApp.initData` на `POST /api/auth`
2. Бэкенд: HMAC-SHA256 валидация → извлечение `user.id` → проверка в БД
3. Существующий пользователь → "С возвращением"
4. Новый → шаг 1 (ФИО)
5. Шаги 2-4: данные через GET-эндпоинты
6. Шаг 6 → `POST /api/register`:

```json
{
  "telegram_id": 123456,
  "full_name": "Иван Иванов",
  "region_id": 1,
  "school_id": 5,
  "subjects": [1, 3],
  "phone": "+79991234567",
  "email": "ivan@mail.ru"
}
```

### Авторизация

Заголовок `X-Telegram-Init-Data` на каждом запросе. FastAPI dependency валидирует и извлекает `telegram_id`. Без валидного initData — 401.

## Фронтенд

Одностраничная форма с 6 шагами, прогресс-бар (6 точек).

| # | Содержимое | UI элемент |
|---|-----------|------------|
| 1 | ФИО | Текстовое поле, валидация ≥2 слов |
| 2 | Регион | Поиск + список кнопок |
| 3 | Школа | Поиск + список кнопок |
| 4 | Предметы | Чекбоксы + кнопка "Готово" |
| 5 | Телефон | Текстовое поле, ≥10 символов |
| 6 | Email | Текстовое поле + "Пропустить" |

### Стилизация

- `Telegram.WebApp.themeParams` для нативного вида
- `Telegram.WebApp.MainButton` — "Далее"/"Готово"
- `Telegram.WebApp.BackButton` — кнопка назад
- Поиск: debounce 300ms → GET `?q=`

### После регистрации

Сообщение об успехе → `Telegram.WebApp.close()`

## MenuButton

При старте бота устанавливаем `MenuButtonWebApp` через `bot.set_chat_menu_button()` — кнопка "Регистрация" открывает Web App URL.
