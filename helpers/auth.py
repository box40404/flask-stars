import hmac
import hashlib
import urllib.parse
import json
import os
from dotenv import load_dotenv

load_dotenv()

def validate_init_data(init_data: str) -> int:
    """Проверка Telegram initData для аутентификации."""
    try:
        bot_token = os.getenv("BOT_TOKEN")
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        parsed_data = urllib.parse.parse_qs(init_data)
        received_hash = parsed_data.get("hash", [""])[0]
        data_check_string = "\n".join(
            f"{k}={v[0]}" for k, v in sorted(parsed_data.items()) if k != "hash"
        )
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        if computed_hash != received_hash:
            raise ValueError("Неверный hash initData")
        user_data = json.loads(parsed_data["user"][0])
        return user_data["id"]
    except Exception as e:
        raise ValueError(f"Ошибка проверки initData: {str(e)}")