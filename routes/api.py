import time
from urllib.parse import unquote
from flask import Blueprint, request, jsonify
from helpers.purchase import check_invoice_status  # Импортируем из оригинального модуля
from fragment_integration import FragmentService
from database import Database
from config import get_star_prices, SUPPORT_URL
from aiocryptopay import AioCryptoPay, Networks
import asyncio
import os
from dotenv import load_dotenv
import hmac
import hashlib
import json
import logging
import concurrent.futures

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

api = Blueprint("api", __name__)
db = Database()
fragment_service = FragmentService()

# Вспомогательная функция для запуска асинхронных операций в синхронном контексте Flask
def run_async(coro):
    """Запуск асинхронной корутины в потоке Flask (Python 3.11)."""
    loop = None
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            logger.debug("Существующий loop закрыт, создаем новый")
            loop = None
    except RuntimeError:
        logger.debug("Нет event loop в потоке, создаем новый")
        loop = None

    if loop is None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)  # Ключ: устанавливаем как current для internal get_event_loop
    try:
        logger.debug(f"Запуск корутины в loop: {coro}")
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())  # Очистка для 3.11
        except Exception as e:
            logger.warning(f"Ошибка shutdown asyncgens: {e}")
        finally:
            loop.close()
            asyncio.set_event_loop(None)

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
            return {"error": "Недействительная подпись данных"}
        
        # Проверка auth_date (данные действительны в течение 24 часов)
        auth_date_str = params.get("auth_date")
        if auth_date_str:
            try:
                auth_date = int(auth_date_str)
                current_time = int(time.time())
                if not (current_time - 86400 <= auth_date <= current_time):
                    return {"error": "Данные авторизации устарели"}
            except ValueError:
                pass  # Игнорируем неверный формат auth_date

        # Извлечение данных пользователя
        user_json = params.get("user", "{}")
        user_data = {}
        if user_json:
            try:
                user_data = json.loads(user_json)
            except json.JSONDecodeError:
                pass  # Игнорируем ошибки парсинга JSON
        
        return {
            "user_id": user_data.get("id"),
            "username": user_data.get("username"),
            "first_name": user_data.get("first_name"),
            "last_name": user_data.get("last_name"),
            "is_bot": user_data.get("is_bot"),
            "language_code": user_data.get("language_code"),
            "query_id": params.get("query_id"),
            "auth_date": params.get("auth_date")
        }
        
    except Exception as e:
        return {"error": f"Ошибка проверки данных: {str(e)}"}

@api.route("/verify-init", methods=["POST"])
def verify_init():
    """Проверка initData от Telegram Web App."""
    try:
        data = request.get_json()
        
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
def get_prices():
    """Получение цен звезд."""
    try:
        prices = run_async(get_star_prices())
        return jsonify(prices)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api.route("/purchase", methods=["POST"])
def create_purchase():
    """Создание покупки и инвойса."""
    try:
        data = request.get_json()
        amount = data.get("amount")
        recipient_username = data.get("recipient_username")
        currency = data.get("currency")
        telegram_user_id = data.get("telegram_user_id")
        
        if not all([amount, recipient_username, currency]):
            return jsonify({"error": "Отсутствуют обязательные поля"}), 400
        if amount < 1:
            return jsonify({"error": "Минимальное количество звезд: 1"}), 400
        
        # Создаем экземпляр AioCryptoPay для этой операции
        crypto = AioCryptoPay(token=os.getenv("CRYPTO_TOKEN"), network=Networks.MAIN_NET)

        prices = run_async(get_star_prices())
        if currency not in prices:
            return jsonify({"error": "Неподдерживаемая валюта"}), 400
        
        price = prices[currency] * amount
        invoice = run_async(crypto.create_invoice(amount=price, asset=currency))
        
        purchase_id = run_async(db.create_purchase(
            user_id=telegram_user_id, item_type="stars", amount=amount, recipient_username=recipient_username,
            currency=currency, price=price, invoice_id=invoice.invoice_id
        ))
        
        if not purchase_id:
            return jsonify({"error": "Ошибка создания покупки"}), 500
        
        # Запускаем фоновую задачу проверки инвойса
        check_invoice_status(purchase_id, invoice.invoice_id)
        
        return jsonify({"purchase_id": purchase_id, "invoice_url": invoice.bot_invoice_url})
    except Exception as e:
        logger.error(f"Ошибка создания покупки: {e}")
        return jsonify({"error": str(e)}), 400

@api.route("/purchase/<int:purchase_id>", methods=["GET"])
def get_purchase(purchase_id):
    """Проверка статуса покупки."""
    try:
        purchase = run_async(db.get_purchase_by_id(str(purchase_id)))
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

