import json
import requests
from src.config import get_settings

s = get_settings()
headers = {"Authorization": s.max_bot_token, "Content-Type": "application/json"}

chat_id = 41778205

# Test 1: open_app with contact_id + web_app (username)
payload = {
    "text": "Тест: username + contact_id",
    "attachments": [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [[
                    {
                        "type": "open_app",
                        "text": "Открыть приложение",
                        "web_app": "id9715405227_bot",
                        "contact_id": 240726372,
                    }
                ]]
            }
        }
    ]
}

print("=== Test 1: username + contact_id ===")
r = requests.post(
    f"https://platform-api.max.ru/messages?chat_id={chat_id}",
    headers=headers,
    json=payload,
)
print(r.status_code, json.dumps(r.json(), indent=2, ensure_ascii=False))

# Test 2: open_app with only contact_id
payload2 = {
    "text": "Тест: только contact_id",
    "attachments": [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [[
                    {
                        "type": "open_app",
                        "text": "Открыть приложение",
                        "contact_id": 240726372,
                    }
                ]]
            }
        }
    ]
}

print("\n=== Test 2: only contact_id ===")
r = requests.post(
    f"https://platform-api.max.ru/messages?chat_id={chat_id}",
    headers=headers,
    json=payload2,
)
print(r.status_code, json.dumps(r.json(), indent=2, ensure_ascii=False))

# Test 3: open_app with URL + contact_id
payload3 = {
    "text": "Тест: URL + contact_id",
    "attachments": [
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [[
                    {
                        "type": "open_app",
                        "text": "Открыть приложение",
                        "web_app": "https://web-production-680ae.up.railway.app",
                        "contact_id": 240726372,
                    }
                ]]
            }
        }
    ]
}

print("\n=== Test 3: URL + contact_id ===")
r = requests.post(
    f"https://platform-api.max.ru/messages?chat_id={chat_id}",
    headers=headers,
    json=payload3,
)
print(r.status_code, json.dumps(r.json(), indent=2, ensure_ascii=False))
