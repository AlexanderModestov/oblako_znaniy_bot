import hashlib
import hmac
import json
import logging
import time
from urllib.parse import unquote

from fastapi import Header, HTTPException

from src.config import get_settings

logger = logging.getLogger(__name__)


def _parse_init_data(init_data: str) -> tuple[dict[str, str], str | None]:
    """Split initData query string manually using unquote (not unquote_plus).

    parse_qs uses unquote_plus internally which converts '+' to space.
    MAX/Telegram sign values with standard percent-decoding where '+' stays '+'.
    This mismatch causes intermittent hash failures when initData contains '+'.
    """
    params = {}
    check_hash = None
    for pair in init_data.split("&"):
        key, _, value = pair.partition("=")
        if key == "hash":
            check_hash = value
        else:
            params[key] = unquote(value)
    return params, check_hash


def _validate_hash(params: dict[str, str], check_hash: str, bot_token: str) -> None:
    data_check_string = "\n".join(
        sorted(f"{k}={v}" for k, v in params.items())
    )
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, check_hash):
        raise ValueError("invalid hash")


def validate_init_data(init_data: str, bot_token: str) -> dict:
    """Validate Telegram WebApp initData and return parsed data."""
    params, check_hash = _parse_init_data(init_data)

    if not check_hash:
        raise ValueError("hash missing")

    _validate_hash(params, check_hash, bot_token)

    auth_date = int(params.get("auth_date", "0"))
    if time.time() - auth_date > 86400:
        raise ValueError("init_data expired")

    user_data = json.loads(params["user"])
    return user_data


def validate_max_init_data(init_data: str, bot_token: str) -> dict:
    """Validate MAX WebApp initData and return parsed data."""
    params, check_hash = _parse_init_data(init_data)

    if not check_hash:
        raise ValueError("hash missing")

    _validate_hash(params, check_hash, bot_token)

    auth_date = int(params.get("auth_date", "0"))
    if time.time() - auth_date > 86400:
        raise ValueError("init_data expired")

    user_data = json.loads(params["user"])
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
            params, check_hash = _parse_init_data(x_max_init_data)
            data_check_string = "\n".join(
                sorted(f"{k}={v}" for k, v in params.items())
            )
            secret_key = hmac.new(b"WebAppData", settings.max_bot_token.encode(), hashlib.sha256).digest()
            computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
            logger.error(
                "Max initData validation failed: %s | initData keys: %s | computed: %s | received: %s | token_prefix: %s | data_check_string_preview: %s",
                e,
                list(params.keys()),
                computed[:16],
                check_hash[:16] if check_hash else "N/A",
                settings.max_bot_token[:8] + "...",
                data_check_string[:100],
            )
            raise HTTPException(status_code=401, detail=str(e))

    raise HTTPException(status_code=401, detail="No auth header provided")
