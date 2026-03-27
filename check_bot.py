import requests
from src.config import get_settings

s = get_settings()
r = requests.get(
    "https://platform-api.max.ru/me",
    headers={"Authorization": s.max_bot_token},
)
print(r.status_code)
print(r.json())
