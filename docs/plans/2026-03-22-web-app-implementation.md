# Telegram Web App Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a Telegram Mini App (Web App) with 6-step onboarding identical to the Telegram bot flow.

**Architecture:** FastAPI backend serving static HTML/JS frontend. Reuses core services (UserService, models, schemas). Telegram initData validated via HMAC-SHA256. Opened via MenuButton in bot chat.

**Tech Stack:** FastAPI, uvicorn, vanilla JS, Telegram WebApp JS SDK, existing SQLAlchemy async stack.

---

### Task 1: Add FastAPI + uvicorn to dependencies

**Files:**
- Modify: `requirements.txt`

**Step 1: Add dependencies**

Add to `requirements.txt`:
```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
```

**Step 2: Install**

Run: `pip install -r requirements.txt`

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "feat(web): add fastapi and uvicorn dependencies"
```

---

### Task 2: Add `WEB_APP_URL` to config

**Files:**
- Modify: `src/config.py`

**Step 1: Add field to Settings**

Add to `Settings` class in `src/config.py`:
```python
web_app_url: str = ""
```

This is the public URL where the web app is hosted (e.g., `https://example.com`). Used by the bot to set MenuButton.

**Step 2: Commit**

```bash
git add src/config.py
git commit -m "feat(config): add web_app_url setting"
```

---

### Task 3: Create `src/web/auth.py` — initData validation

**Files:**
- Create: `src/web/__init__.py` (empty)
- Create: `src/web/auth.py`

**Step 1: Implement HMAC-SHA256 validation**

Create `src/web/auth.py`:
```python
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, unquote

from fastapi import Header, HTTPException

from src.config import get_settings


def validate_init_data(init_data: str, bot_token: str) -> dict:
    """Validate Telegram WebApp initData and return parsed data."""
    parsed = parse_qs(init_data)

    check_hash = parsed.get("hash", [None])[0]
    if not check_hash:
        raise ValueError("hash missing")

    # Build data-check-string: sorted key=value pairs excluding hash
    items = []
    for key, values in parsed.items():
        if key == "hash":
            continue
        items.append(f"{key}={unquote(values[0])}")
    data_check_string = "\n".join(sorted(items))

    # HMAC-SHA256 validation
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, check_hash):
        raise ValueError("invalid hash")

    # Check auth_date is not too old (allow 24 hours)
    auth_date = int(parsed.get("auth_date", [0])[0])
    if time.time() - auth_date > 86400:
        raise ValueError("init_data expired")

    # Parse user JSON
    user_data = json.loads(unquote(parsed["user"][0]))
    return user_data


async def get_telegram_user(x_telegram_init_data: str = Header()) -> dict:
    """FastAPI dependency: validate initData header, return user dict with 'id' field."""
    try:
        settings = get_settings()
        user_data = validate_init_data(x_telegram_init_data, settings.bot_token)
        return user_data
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=401, detail=str(e))
```

**Step 2: Commit**

```bash
git add src/web/__init__.py src/web/auth.py
git commit -m "feat(web): add Telegram initData HMAC-SHA256 validation"
```

---

### Task 4: Create `src/web/routes.py` — API endpoints

**Files:**
- Create: `src/web/routes.py`

**Step 1: Implement all endpoints**

Create `src/web/routes.py`:
```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_session
from src.core.schemas import UserCreate
from src.core.services.user import UserService
from src.web.auth import get_telegram_user

router = APIRouter(prefix="/api")
user_service = UserService()


async def get_session():
    session_factory = get_async_session()
    async with session_factory() as session:
        yield session


@router.post("/auth")
async def auth(
    tg_user: dict = Depends(get_telegram_user),
    session: AsyncSession = Depends(get_session),
):
    telegram_id = tg_user["id"]
    user = await user_service.get_by_telegram_id(session, telegram_id)
    return {
        "telegram_id": telegram_id,
        "status": "existing" if user else "new",
        "full_name": user.full_name if user else None,
    }


@router.get("/regions")
async def regions(
    q: str = Query(default="", max_length=100),
    tg_user: dict = Depends(get_telegram_user),
    session: AsyncSession = Depends(get_session),
):
    if q:
        return await user_service.search_regions(session, q, limit=50)
    return await user_service.get_all_regions(session)


@router.get("/schools/{region_id}")
async def schools(
    region_id: int,
    q: str = Query(default="", max_length=100),
    tg_user: dict = Depends(get_telegram_user),
    session: AsyncSession = Depends(get_session),
):
    if q:
        return await user_service.search_schools(session, region_id, q, limit=50)
    return await user_service.get_schools_by_region(session, region_id)


@router.get("/subjects")
async def subjects(
    tg_user: dict = Depends(get_telegram_user),
    session: AsyncSession = Depends(get_session),
):
    return await user_service.get_all_subjects(session)


@router.post("/register")
async def register(
    data: UserCreate,
    tg_user: dict = Depends(get_telegram_user),
    session: AsyncSession = Depends(get_session),
):
    # Ensure telegram_id matches authenticated user
    data.telegram_id = tg_user["id"]
    user = await user_service.create_user(session, data)
    return {"ok": True, "user_id": user.id}
```

**Step 2: Commit**

```bash
git add src/web/routes.py
git commit -m "feat(web): add API routes (auth, regions, schools, subjects, register)"
```

---

### Task 5: Create `src/web/app.py` — FastAPI application

**Files:**
- Create: `src/web/app.py`

**Step 1: Implement app with static files**

Create `src/web/app.py`:
```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.web.routes import router

app = FastAPI(title="AITSOK Web App")
app.include_router(router)

static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
```

**Step 2: Commit**

```bash
git add src/web/app.py
git commit -m "feat(web): add FastAPI app with static files mount"
```

---

### Task 6: Create frontend — `index.html`

**Files:**
- Create: `src/web/static/index.html`

**Step 1: Write HTML**

Create `src/web/static/index.html` — single page with 6 step containers:
- Step 1: ФИО input
- Step 2: Region search + list
- Step 3: School search + list
- Step 4: Subjects checkboxes
- Step 5: Phone input
- Step 6: Email input + skip
- Success screen

Include Telegram WebApp JS SDK via `<script src="https://telegram.org/js/telegram-web-app.js"></script>`.

Link `style.css` and `app.js`.

**Step 2: Commit**

```bash
git add src/web/static/index.html
git commit -m "feat(web): add registration form HTML"
```

---

### Task 7: Create frontend — `style.css`

**Files:**
- Create: `src/web/static/style.css`

**Step 1: Write styles**

Use CSS custom properties mapped from `Telegram.WebApp.themeParams`:
- `--tg-theme-bg-color`
- `--tg-theme-text-color`
- `--tg-theme-hint-color`
- `--tg-theme-button-color`
- `--tg-theme-button-text-color`
- `--tg-theme-secondary-bg-color`

Style:
- Progress bar (6 dots)
- Step containers (hidden by default, `.active` visible)
- Input fields, search field
- Item list buttons (for region/school)
- Checkbox grid (for subjects)
- Validation error messages

**Step 2: Commit**

```bash
git add src/web/static/style.css
git commit -m "feat(web): add Telegram-themed styles"
```

---

### Task 8: Create frontend — `app.js`

**Files:**
- Create: `src/web/static/app.js`

**Step 1: Implement step logic**

Core structure:
```javascript
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const initData = tg.initData;
let currentStep = 0;
const formData = {};

// API helper: adds X-Telegram-Init-Data header to every request
async function api(method, url, body) { ... }

// Step management
function showStep(n) { ... }  // hide all, show step n, update progress dots

// Step 1: ФИО
// Validate >= 2 words on MainButton click

// Step 2: Regions
// Fetch /api/regions on enter, search with debounce, render as clickable list

// Step 3: Schools
// Fetch /api/schools/{regionId} on enter, search with debounce

// Step 4: Subjects
// Fetch /api/subjects, render as toggleable checkboxes

// Step 5: Phone
// Text input, validate >= 10 chars

// Step 6: Email
// Text input + "Пропустить" button via tg.MainButton

// Submit: POST /api/register with formData
// On success: show success screen, tg.close() after 2s

// MainButton: "Далее" on steps 1-5, "Готово" on step 6
// BackButton: show on steps 2+, go back one step

// Init: POST /api/auth → if existing → show success, if new → showStep(1)
```

**Step 2: Commit**

```bash
git add src/web/static/app.js
git commit -m "feat(web): add registration flow JS logic"
```

---

### Task 9: Add MenuButton setup to bot startup

**Files:**
- Modify: `src/main.py`

**Step 1: Set MenuButton on startup**

Add to `main()` in `src/main.py`, after bot creation and before polling:
```python
from aiogram.types import MenuButtonWebApp, WebAppInfo

settings = get_settings()
if settings.web_app_url:
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Регистрация",
            web_app=WebAppInfo(url=settings.web_app_url),
        )
    )
```

**Step 2: Commit**

```bash
git add src/main.py
git commit -m "feat(bot): set MenuButton to open Web App"
```

---

### Task 10: Verify end-to-end

**Step 1: Start the web server**

Run: `uvicorn src.web.app:app --reload --port 8080`

**Step 2: Verify API**

Run:
```bash
curl http://localhost:8080/api/regions -H "X-Telegram-Init-Data: test"
```
Expected: 401 (invalid initData) — confirms auth works.

**Step 3: Verify static files**

Open `http://localhost:8080/` in browser — should show the registration form HTML.

**Step 4: Commit final state if any fixes needed**
