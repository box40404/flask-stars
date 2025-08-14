from quart import Blueprint, request, jsonify, current_app
from helpers.purchase import check_invoice_status, process_stars_purchase
from config import get_star_prices, SUPPORT_URL, ADMIN_ID
import asyncio
import os
from dotenv import load_dotenv
import hmac
import hashlib
import json
import logging
from urllib.parse import unquote

# Настройка логирования
logging.basicConfig(level=logging.INFO, filename="logs/site.log")
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
            return {
                "user_id": user.get("id"),
                "username": user.get("username", "").lstrip("@"),
                "first_name": user.get("first_name"),
                "last_name": user.get("last_name")
            }
        except json.JSONDecodeError:
            return {"error": "Неверный формат данных пользователя"}
    except Exception as e:
        return {"error": f"Ошибка проверки initData: {str(e)}"}

@api.route("/verify-init", methods=["POST"])
async def verify_init():
    """Проверка initData от Telegram Web App."""
    data = await request.get_json()
    init_data = data.get("initData")
    if not init_data:
        return jsonify({"error": "No initData provided"}), 400
    
    result = verify_init_data(init_data)
    if "error" in result:
        logger.error(f"Verify initData failed: {result['error']}")
        return jsonify(result), 400
    
    db = current_app.config["DB"]
    user_id = result["user_id"]
    username = result["username"]
    
    # Проверяем, существует ли пользователь
    user = await db.get_user(user_id)
    if not user:
        await db.create_user(username=username, fullname=f"{result.get('first_name', '')} {result.get('last_name', '')}".strip())
    
    return jsonify({"user_id": user_id, "username": username})

@api.route("/prices", methods=["GET"])
async def get_prices():
    """Получение цен на звезды."""
    try:
        prices = await get_star_prices()
        return jsonify(prices)
    except Exception as e:
        logger.error(f"Error getting prices: {str(e)}")
        return jsonify({"error": str(e)}), 500

@api.route("/bonus_balance", methods=["POST"])
async def get_bonus_balance():
    """Получение бонусного баланса пользователя."""
    data = await request.get_json()
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "No user_id provided"}), 400
    db = current_app.config["DB"]
    try:
        balance = await db.get_bonus_balance(user_id)
        return jsonify({"bonus_balance": balance})
    except Exception as e:
        logger.error(f"Error getting bonus balance for user {user_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@api.route("/purchase", methods=["POST"])
async def create_purchase():
    """Создание покупки с учетом бонусов."""
    data = await request.get_json()
    amount = data.get("amount")
    recipient_username = data.get("recipient_username")
    currency = data.get("currency")
    user_id = data.get("user_id")  # Может быть None для неавторизованных пользователей
    
    if not all([amount, recipient_username, currency]):
        return jsonify({"error": "Отсутствуют обязательные поля"}), 400
    if amount < 1:
        return jsonify({"error": "Минимальное количество звезд: 1"}), 400
    
    crypto = current_app.config["CRYPTO"]
    db = current_app.config["DB"]
    bot = current_app.config["BOT"]
    prices = await get_star_prices()
    if currency not in prices:
        return jsonify({"error": "Неподдерживаемая валюта"}), 400
    
    try:
        # Рассчитываем цену
        price = amount * prices[currency]
        bonus_stars_used = 0.0
        bonus_discount = 0.0
        bonus_applied = False
        
        # Проверяем бонусный баланс, если пользователь авторизован и покупает для себя
        if user_id:
            user = await db.get_user(user_id)
            if user and user["username"] and recipient_username.lower().lstrip("@") == user["username"].lower().lstrip("@"):
                bonus_balance = await db.get_bonus_balance(user_id)
                if bonus_balance > 0:
                    bonus_applied = True
                    bonus_discount = min(bonus_balance * prices[currency], price)
                    bonus_stars_used = min(bonus_balance, bonus_discount / prices[currency])
                    price -= bonus_discount

        # Если бонусов хватает на весь заказ
        if price <= 0.001:
            purchase_id = await db.create_purchase(
                user_id=user_id or 0,
                item_type="stars",
                amount=amount,
                recipient_username=recipient_username.lstrip("@"),
                currency=currency,
                price=0.0,
                invoice_id="bonus_payment",
                bonus_stars_used=bonus_stars_used,
                bonus_discount=bonus_discount
            )
            # Списываем бонусы
            if bonus_stars_used > 0:
                await db.update_bonus_balance(user_id, bonus_balance - bonus_stars_used)
                await db.log_transaction(
                    purchase_id,
                    "bonus_payment",
                    "success",
                    f"Заказ оплачен бонусами: {bonus_stars_used:.2f} звёзд"
                )
            # Обновляем статус
            await db.update_purchase_status(purchase_id, "paid")
            await db.update_purchase_status(purchase_id, "processing")
            # Уведомляем пользователя
            if user_id:
                try:
                    bonus_msg = f"\nИспользовано бонусов: {bonus_stars_used:.2f} звёзд\nОстаток бонусов: {(await db.get_bonus_balance(user_id)):.2f} звёзд" if bonus_applied else ""
                    await bot.send_message(
                        chat_id=user_id,
                        text=f"<b>✅ Заказ оплачен бонусами!</b>\n\n"
                             f"Товар: {amount} Звёзд ⭐️\n"
                             f"Получатель: @{recipient_username.lstrip('@')}\n"
                             f"{bonus_msg}\n"
                             f"⚙️ Обрабатываем ваш заказ...",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Purchase {purchase_id}: Failed to send bonus payment notification: {str(e)}")
            # Уведомляем администраторов
            try:
                bonus_msg = f"\nИспользовано бонусов: {bonus_stars_used:.2f} звёзд" if bonus_applied else ""
                await bot.send_message(
                    chat_id=ADMIN_ID[0],
                    text=f"<b>💰 Заказ оплачен бонусами!</b>\n\n"
                         f"Покупка ID: {purchase_id}\n"
                         f"Пользователь: {user_id or 'Неавторизован'}\n"
                         f"Товар: {amount} Звёзд ⭐️\n"
                         f"Получатель: @{recipient_username.lstrip('@')}\n"
                         f"{bonus_msg}\n"
                         f"🔄 Начинаем обработку заказа...",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Purchase {purchase_id}: Failed to send admin notification: {str(e)}")
            # Запускаем обработку
            asyncio.create_task(process_stars_purchase(purchase_id, "bonus_payment"))
            return jsonify({"purchase_id": purchase_id, "invoice_url": None, "price": 0.0, "bonus_stars_used": bonus_stars_used, "bonus_discount": bonus_discount})
        
        # Создаем инвойс, если нужна оплата
        invoice = await crypto.create_invoice(
            asset=currency,
            amount=price,
            description=f"Purchase of {amount} stars for @{recipient_username}"
        )
        purchase_id = await db.create_purchase(
            user_id=user_id or 0,
            item_type="stars",
            amount=amount,
            recipient_username=recipient_username.lstrip("@"),
            currency=currency,
            price=price,
            invoice_id=str(invoice.invoice_id),
            bonus_stars_used=bonus_stars_used,
            bonus_discount=bonus_discount
        )

        asyncio.create_task(check_invoice_status(purchase_id, str(invoice.invoice_id)))
        return jsonify({"purchase_id": purchase_id, "invoice_url": invoice.bot_invoice_url, "price": price, "bonus_stars_used": bonus_stars_used, "bonus_discount": bonus_discount})
    except Exception as e:
        logger.error(f"Error creating purchase: {str(e)}")
        return jsonify({"error": str(e)}), 500

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
            "error_message": purchase["error_message"],
            "bonus_stars_used": purchase["bonus_stars_used"],
            "bonus_discount": purchase["bonus_discount"]
        })
    except Exception as e:
        logger.error(f"Error getting purchase status {purchase_id}: {str(e)}")
        return jsonify({"error": str(e)}), 400

@api.route("/support", methods=["GET"])
def get_support():
    """Получение ссылки на поддержку."""
    return jsonify({"support_url": SUPPORT_URL})