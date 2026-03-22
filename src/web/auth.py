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
