import hashlib
import hmac
import json
import logging
import time
from operator import itemgetter
from urllib.parse import parse_qsl, unquote

from fastapi import Header, HTTPException

from src.config import get_settings

logger = logging.getLogger(__name__)


def _validate(init_data: str, bot_token: str) -> dict:
    """Validate WebApp initData (Telegram & MAX use the same scheme).

    Implementation follows the official MAX documentation exactly:
    https://dev.max.ru/docs/webapps/validation
    """
    # parse_qsl decodes values via unquote_plus and preserves blank values
    params = dict(parse_qsl(init_data, keep_blank_values=True))

    original_hash = params.pop("hash", None)
    if not original_hash:
        raise ValueError("hash missing")

    # Sort alphabetically, join as key=value with newlines
    params_to_sign = sorted(params.items(), key=itemgetter(0))
    launch_params = "\n".join(f"{k}={v}" for k, v in params_to_sign)

    # HMAC-SHA256: secret = HMAC("WebAppData", token), hash = HMAC(secret, data)
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode(),
        digestmod=hashlib.sha256,
    ).digest()
    computed = hmac.new(
        key=secret_key,
        msg=launch_params.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed, original_hash):
        raise ValueError("invalid hash")

    # Check auth_date freshness (24 hours)
    auth_date = int(params.get("auth_date", "0"))
    if time.time() - auth_date > 86400:
        raise ValueError("init_data expired")

    user_data = json.loads(params["user"])
    return user_data


def validate_init_data(init_data: str, bot_token: str) -> dict:
    """Validate Telegram WebApp initData and return parsed user data."""
    return _validate(init_data, bot_token)


def validate_max_init_data(init_data: str, bot_token: str) -> dict:
    """Validate MAX WebApp initData and return parsed user data."""
    return _validate(init_data, bot_token)


async def get_telegram_user(x_telegram_init_data: str = Header()) -> dict:
    """FastAPI dependency: validate initData header, return user dict with 'id' field."""
    try:
        settings = get_settings()
        return validate_init_data(x_telegram_init_data, settings.bot_token)
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
            # Debug logging
            params = dict(parse_qsl(x_max_init_data, keep_blank_values=True))
            received = params.pop("hash", None)
            params_to_sign = sorted(params.items(), key=itemgetter(0))
            launch_params = "\n".join(f"{k}={v}" for k, v in params_to_sign)
            secret_key = hmac.new(key=b"WebAppData", msg=settings.max_bot_token.encode(), digestmod=hashlib.sha256).digest()
            computed = hmac.new(key=secret_key, msg=launch_params.encode(), digestmod=hashlib.sha256).hexdigest()
            logger.error(
                "Max initData validation failed: %s | initData keys: %s | computed: %s | received: %s | token_prefix: %s | data_check_string_preview: %s",
                e,
                list(params.keys()),
                computed[:16],
                received[:16] if received else "N/A",
                settings.max_bot_token[:8] + "...",
                launch_params[:100],
            )
            raise HTTPException(status_code=401, detail=str(e))

    raise HTTPException(status_code=401, detail="No auth header provided")
