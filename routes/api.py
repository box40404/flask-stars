from quart import Blueprint, request, jsonify, current_app
from helpers.purchase import check_invoice_status
from config import get_star_prices, SUPPORT_URL
import asyncio
import os
from dotenv import load_dotenv
import hmac
import hashlib
import json
import logging
from urllib.parse import unquote

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

api = Blueprint("api", __name__)

def verify_init_data(init_data_raw: str) -> dict:
    """Проверка подлинности initData от Telegram Web App с URL-декодированием."""
    try:
        bot_token = os.getenv("BOT_TOKEN")
        if not bot_token:
            return {"error": "BOT_TOKEN не настроен"}
        
        # URL-декодирование initData
        try:
            init_data_decoded = unquote(init_data_raw)
        except Exception as e:
            return {"error": f"Неверный формат initData: {str(e)}"}

        # Парсинг параметров
        params = {}
        pairs = init_data_decoded.split("&")
        for pair in pairs:
            if "=" in pair:
                key, value = pair.split("=", 1)
                params[key] = value
        
        # Извлечение хеша
        received_hash = params.pop("hash", None)
        if not received_hash:
            return {"error": "Отсутствует hash в данных"}
        
        # Создание секретного ключа
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        
        # Создание строки для проверки
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        
        # Вычисление хеша
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        # Проверка хеша
        if computed_hash != received_hash:
            return {"error": "Неверный hash в данных"}
        
        # Извлечение данных пользователя
        user_str = params.get("user")
        if not user_str:
            return {"error": "Отсутствует параметр user"}
        
        try:
            user = json.loads(user_str)
        except json.JSONDecodeError:
            return {"error": "Неверный формат user data"}
        
        return {
            "user_id": user.get("id"),
            "username": user.get("username"),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
            "photo_url": user.get("photo_url")
        }
    except Exception as e:
        return {"error": f"Ошибка проверки initData: {str(e)}"}

@api.route("/verify-init", methods=["POST"])
async def verify_init():
    """Проверка initData от Telegram Web App."""
    try:
        data = await request.get_json()
        init_data = data.get("initData")
        if not init_data:
            return jsonify({"error": "Отсутствует initData"}), 400
        
        result = verify_init_data(init_data)
        
        if "error" in result:
            return jsonify(result), 401
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Ошибка сервера: {str(e)}"}), 500

@api.route("/prices", methods=["GET"])
async def get_prices():
    """Получение цен звезд."""
    try:
        prices = await get_star_prices()
        return jsonify(prices)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.route("/purchase", methods=["POST"])
async def create_purchase():
    """Создание покупки и инвойса."""
    try:
        data = await request.get_json()
        amount = data.get("amount")
        recipient_username = data.get("recipient_username")
        currency = data.get("currency")
        telegram_user_id = data.get("telegram_user_id")
        
        if not all([amount, recipient_username, currency]):
            return jsonify({"error": "Отсутствуют обязательные поля"}), 400
        if amount < 1:
            return jsonify({"error": "Минимальное количество звезд: 1"}), 400
        
        # Используем глобальный экземпляр AioCryptoPay
        crypto = current_app.config["CRYPTO"]
        db = current_app.config["DB"]

        prices = await get_star_prices()
        if currency not in prices:
            return jsonify({"error": "Неподдерживаемая валюта"}), 400
        
        price = prices[currency] * amount
        invoice = await crypto.create_invoice(amount=price, asset=currency)
        
        purchase_id = await db.create_purchase(
            user_id=telegram_user_id, item_type="stars", amount=amount, recipient_username=recipient_username,
            currency=currency, price=price, invoice_id=invoice.invoice_id
        )
        
        if not purchase_id:
            return jsonify({"error": "Ошибка создания покупки"}), 500
        
        # Запускаем фоновую задачу проверки инвойса
        asyncio.create_task(check_invoice_status(purchase_id, invoice.invoice_id))
        
        return jsonify({"purchase_id": purchase_id, "invoice_url": invoice.bot_invoice_url})
    except Exception as e:
        logger.error(f"Ошибка создания покупки: {e}")
        return jsonify({"error": str(e)}), 400

@api.route("/purchase/<int:purchase_id>", methods=["GET"])
async def get_purchase(purchase_id):
    """Проверка статуса покупки."""
    try:
        db = current_app.config["DB"]
        purchase = await db.get_purchase_by_id(str(purchase_id))
        if not purchase:
            return jsonify({"error": "Покупка не найдена"}), 404
        return jsonify({
            "purchase_id": purchase["id"],
            "status": purchase["status"],
            "error_message": purchase["error_message"]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@api.route("/support", methods=["GET"])
def get_support():
    """Получение ссылки на поддержку."""
    return jsonify({"support_url": SUPPORT_URL})