import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qs, unquote

from fastapi import Header, HTTPException

from src.config import get_settings

logger = logging.getLogger(__name__)


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


def validate_max_init_data(init_data: str, bot_token: str) -> dict:
    """Validate MAX WebApp initData and return parsed data.

    MAX uses the same HMAC-SHA256 scheme as Telegram but may include
    fields with empty values (e.g. start_param=).  The standard
    parse_qs drops them by default which breaks the hash check.
    """
    parsed = parse_qs(init_data, keep_blank_values=True)

    check_hash = parsed.get("hash", [None])[0]
    if not check_hash:
        raise ValueError("hash missing")

    items = []
    for key, values in parsed.items():
        if key == "hash":
            continue
        items.append(f"{key}={unquote(values[0])}")
    data_check_string = "\n".join(sorted(items))

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, check_hash):
        raise ValueError("invalid hash")

    auth_date = int(parsed.get("auth_date", [0])[0])
    if time.time() - auth_date > 86400:
        raise ValueError("init_data expired")

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


async def get_platform_user(
    x_telegram_init_data: str | None = Header(default=None),
    x_max_init_data: str | None = Header(default=None),
) -> dict:
    """FastAPI dependency: validate initData from either platform."""
    settings = get_settings()

    if x_telegram_init_data:
        try:
            user_data = validate_init_data(x_telegram_init_data, settings.bot_token)
            user_data["platform"] = "telegram"
            return user_data
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=401, detail=str(e))

    if x_max_init_data:
        try:
            user_data = validate_max_init_data(x_max_init_data, settings.max_bot_token)
            user_data["platform"] = "max"
            return user_data
        except (ValueError, KeyError) as e:
            # Debug: log data_check_string for troubleshooting
            parsed = parse_qs(x_max_init_data)
            items = []
            for key, values in parsed.items():
                if key == "hash":
                    continue
                items.append(f"{key}={unquote(values[0])}")
            data_check_string = "\n".join(sorted(items))
            secret_key = hmac.new(b"WebAppData", settings.max_bot_token.encode(), hashlib.sha256).digest()
            computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
            received = parsed.get("hash", [None])[0]
            logger.error(
                "Max initData validation failed: %s | initData keys: %s | computed: %s | received: %s | token_prefix: %s | data_check_string_preview: %s",
                e,
                list(parsed.keys()),
                computed[:16],
                received[:16] if received else "N/A",
                settings.max_bot_token[:8] + "...",
                data_check_string[:100],
            )
            raise HTTPException(status_code=401, detail=str(e))

    raise HTTPException(status_code=401, detail="No auth header provided")
