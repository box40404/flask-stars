from io import BytesIO
import aiohttp
import qrcode
from quart import current_app
import logging
import asyncio
from config import ADMIN_ID, TON_WALLET_ADDRESS, TONCENTER_API_KEY

logging.basicConfig(filename="logs/site.log", level=logging.INFO)

last_checked_lt = 0
last_checked_hash = ""
pending_ton_purchases = {}  # Кэш: {comment: purchase_id} для pending TON покупок

async def poll_ton_transactions():
    """Фоновая задача для опроса транзакций TON каждые 5 секунд"""
    db = current_app.config["DB"]
    global last_checked_lt, last_checked_hash
    processed_lt = set()  # Кэш для отслеживания обработанных lt
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "address": TON_WALLET_ADDRESS,
                    "limit": 20,  # Последние 20 транзакций
                }
                if TONCENTER_API_KEY:
                    params["api_key"] = TONCENTER_API_KEY
                
                async with session.get(f"https://testnet.toncenter.com/api/v2/getTransactions", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        transactions = data.get("result", [])
                        
                        for tx in transactions:  # Обрабатываем в порядке API (от новых к старым)
                            tx_lt = int(tx["transaction_id"]["lt"])
                            
                            # Пропускаем уже обработанные транзакции
                            if tx_lt in processed_lt:
                                continue
                            
                            in_msg = tx.get("in_msg", {})
                            value_nano = int(in_msg["value"])
                            value_ton = value_nano / 1e9
                            comment = in_msg.get("message", "").strip()  # Комментарий (payload)
                            if comment in pending_ton_purchases:
                                purchase_id = pending_ton_purchases[comment]
                                purchase = await db.get_purchase_by_id(str(purchase_id))
                                
                                if purchase and purchase["status"] == "pending":
                                    expected_price = purchase["price"]
                                    if abs(value_ton - expected_price) < 0.01:  # Допуск на fees
                                        # Подтверждаем платеж
                                        await db.update_purchase_status(purchase_id, "paid")
                                        await db.log_transaction(
                                            purchase_id,
                                            "payment_confirmed",
                                            "success",
                                            f"TON платеж подтвержден: {value_ton} TON, tx_hash: {tx['transaction_id']['hash']}"
                                        )
                                        await db.update_purchase_status(purchase_id, "processing")

                                        del pending_ton_purchases[comment]
                                        
                                        # Запускаем обработку
                                        asyncio.create_task(process_stars_purchase(purchase_id))
                                        
                                        # Удаляем из pending
                                        del pending_ton_purchases[comment]
                            
                            # Отмечаем транзакцию как обработанную
                            processed_lt.add(tx_lt)
                        # Ограничиваем размер кэша
                        if len(processed_lt) > 1000:
                            processed_lt.clear()
                                
        except Exception as e:
            logging.error(f"Ошибка при опросе TON транзакций: {e}")
        
        await asyncio.sleep(5)  # Каждые 5 секунд

async def generate_ton_qr_code(address: str, amount: float, comment: str) -> BytesIO:
    """Генерация QR-кода для TON-платежа"""

    # Конвертируем сумму из TON в нанотоны (1 TON = 10^9 нанотон)
    amount_nanoton = int(amount * 1_000_000_000)

    # Формируем TON URI
    ton_uri = f"ton://transfer/{address}?amount={amount_nanoton}&text={comment}"
    
    # Создаем QR-код
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(ton_uri)
    qr.make(fit=True)
    
    # Создаем изображение
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Сохраняем в BytesIO для отправки
    img_byte_arr = BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return img_byte_arr

async def check_invoice_status(purchase_id: int, invoice_id: str):
    """Проверка статуса инвойса каждые 2 секунды в течение 15 минут."""
    crypto = current_app.config["CRYPTO"]
    bot = current_app.config["BOT"]
    db = current_app.config["DB"]
    fragment_service = current_app.config["FRAGMENT"]
    
    try:
        max_duration = 15 * 60  # 15 минут в секундах
        interval = 5  # Интервал проверки: 2 секунды
        max_attempts = max_duration // interval
        attempt = 1

        while attempt <= max_attempts:
            try:
                purchase = await db.get_purchase_by_id(str(purchase_id))
                if purchase["currency"] == "TON":
                    if purchase["status"] in ["paid", "processing", "completed"]:
                        return
                else:
                    invoices = await crypto.get_invoices(invoice_ids=[int(invoice_id)])
                    if invoices[0].status == "paid":
                        # Инвойс оплачен, запускаем обработку покупки
                        await process_stars_purchase(purchase_id, invoice_id)
                        return
                    elif invoices[0].status in ["expired", "cancelled"]:
                        # Инвойс истек или отменен
                        await db.update_purchase_status(purchase_id, "cancelled", error_message=f"Invoice {invoices[0].status}")
                        await db.log_transaction(purchase_id, "invoice_failed", "error", f"Invoice {invoices[0].status}")
                        logging.error(f"Purchase {purchase_id}: Invoice {invoices[0].status}")
                        # Удаляем инвойс
                        try:
                            await crypto.delete_invoice(int(invoice_id))
                            logging.info(f"Purchase {purchase_id}: Invoice {invoice_id} deleted")
                        except Exception as e:
                            logging.error(f"Purchase {purchase_id}: Failed to delete invoice {invoice_id}: {str(e)}")
                        # Отправляем уведомление об отмене
                        if purchase and purchase.get("user_id"):
                            try:
                                await bot.send_message(
                                    chat_id=purchase["user_id"],
                                    text=f"Покупка #{purchase_id} на {purchase['amount']} звезд отменена: счет истек или был отменен."
                                )
                            except Exception as e:
                                logging.error(f"Purchase {purchase_id}: Failed to send cancellation notification: {str(e)}")
                        return
                # Ждем 2 секунды перед следующей попыткой
                await asyncio.sleep(interval)
                attempt += 1
            except Exception as e:
                logging.error(f"Purchase {purchase_id}: Invoice check failed on attempt {attempt}: {str(e)}")
                await db.log_transaction(purchase_id, "invoice_check_failed", "error", f"Attempt {attempt}, error: {str(e)}")
                await asyncio.sleep(interval)
                attempt += 1

        # Если 15 минут истекли, отменяем покупку
        if purchase['currency'] == "TON" and invoice_id in pending_ton_purchases:
            await db.update_purchase_status(purchase_id, "cancelled", error_message="Invoice check timeout")
            del pending_ton_purchases[invoice_id]
        else:
            await db.update_purchase_status(purchase_id, "cancelled", error_message="Invoice check timeout")
            await db.log_transaction(purchase_id, "invoice_timeout", "error", "Invoice check timeout after 15 minutes")
            logging.error(f"Purchase {purchase_id}: Invoice check timeout after {max_attempts} attempts")
            try:
                await crypto.delete_invoice(int(invoice_id))
                logging.info(f"Purchase {purchase_id}: Invoice {invoice_id} deleted due to timeout")
            except Exception as e:
                logging.error(f"Purchase {purchase_id}: Failed to delete invoice {invoice_id}: {str(e)}")
            # Отправляем уведомление об отмене
            purchase = await db.get_purchase_by_id(str(purchase_id))
            if purchase and purchase.get("user_id"):
                try:
                    await bot.send_message(
                        chat_id=purchase["user_id"],
                        text=f"Покупка #{purchase_id} на {purchase['amount']} звезд отменена: время ожидания оплаты (15 минут) истекло."
                    )
                except Exception as e:
                    logging.error(f"Purchase {purchase_id}: Failed to send timeout notification: {str(e)}")
    except Exception as e:
        await db.update_purchase_status(purchase_id, "cancelled", error_message=f"Unexpected error: {str(e)}")
        await db.log_transaction(purchase_id, "check_invoice_failed", "error", f"Unexpected error: {str(e)}")
        logging.error(f"Purchase {purchase_id}: Check invoice failed - {str(e)}")
        try:
            await crypto.delete_invoice(int(invoice_id))
            logging.info(f"Purchase {purchase_id}: Invoice {invoice_id} deleted due to unexpected error")
        except Exception as e:
            logging.error(f"Purchase {purchase_id}: Failed to delete invoice {invoice_id}: {str(e)}")
        # Отправляем уведомление об ошибке
        purchase = await db.get_purchase_by_id(str(purchase_id))
        if purchase and purchase.get("user_id"):
            try:
                await bot.send_message(
                    chat_id=purchase["user_id"],
                    text=f"Покупка #{purchase_id} на {purchase['amount']} звезд не удалась: {str(e)}"
                )
            except Exception as e:
                logging.error(f"Purchase {purchase_id}: Failed to send error notification: {str(e)}")

async def process_stars_purchase(purchase_id: int, invoice_id: str = None):
    """Обработка покупки звезд после подтверждения оплаты."""
    crypto = current_app.config["CRYPTO"]
    bot = current_app.config["BOT"]
    db = current_app.config["DB"]
    fragment_service = current_app.config["FRAGMENT"]
    
    try:
        purchase = await db.get_purchase_by_id(str(purchase_id))
        if not purchase:
            logging.error(f"Purchase {purchase_id}: Not found")
            return
        await db.log_transaction(purchase_id, "processing_started", "info", "Начата обработка заказа")
        logging.info(f"Purchase {purchase_id}: Started processing for {purchase['recipient_username']}")

        # Если покупка уже оплачена бонусами
        if purchase["invoice_id"] == "bonus_payment":
            amount = purchase["amount"]
        else:
            amount = purchase["amount"] - int(purchase["bonus_stars_used"])  # Учитываем бонусы

        # Списываем бонусы
        if purchase["user_id"]:
            if purchase["bonus_stars_used"] > 0:
                await db.update_bonus_balance(purchase["user_id"], -purchase["bonus_stars_used"])

        # Отправляем звезды через Fragment API, если есть что отправлять
        if amount > 0:
            result = await fragment_service.process_stars_purchase(amount, purchase["recipient_username"])
            if not result["success"]:
                await db.update_purchase_status(purchase_id, "failed", error_message=result["error"])
                await db.log_transaction(purchase_id, "delivery_failed", "error", f"Ошибка: {result['error']}")
                logging.error(f"Purchase {purchase_id}: Failed - {result['error']}")
                # Отправляем уведомление об ошибке
                if purchase["user_id"]:
                    try:
                        await bot.send_message(
                            chat_id=purchase["user_id"],
                            text=f"Покупка #{purchase_id} на {purchase['amount']} звезд не удалась: {result['error']}"
                        )
                    except Exception as e:
                        logging.error(f"Purchase {purchase_id}: Failed to send failure notification: {str(e)}")
                return
        else:
            result = {"success": True, "transaction_id": purchase["invoice_id"]}

        # Если покупка успешна
        await db.update_purchase_status(purchase_id, "completed", result.get("transaction_id"))
        await db.log_transaction(purchase_id, "stars_delivered", "success", f"Transaction ID: {result.get('transaction_id')}")
        logging.info(f"Purchase {purchase_id}: Stars delivered")
        # Отправляем уведомление об успехе
        if purchase["user_id"]:
            try:
                bonus_msg = f" (использовано {purchase['bonus_stars_used']:.2f} бонусов)" if purchase["bonus_stars_used"] > 0 else ""
                await bot.send_message(
                    chat_id=purchase["user_id"],
                    text=f"Покупка #{purchase_id} на {purchase['amount']} звезд успешно завершена!{bonus_msg} Звезды отправлены на @{purchase['recipient_username']}."
                )
            except Exception as e:
                logging.error(f"Purchase {purchase_id}: Failed to send success notification: {str(e)}")

        # Уведомляем администраторов
        try:
            bonus_msg = f"\nИспользовано бонусов: {purchase['bonus_stars_used']:.2f} звёзд" if purchase["bonus_stars_used"] > 0 else ""
            await bot.send_message(
                chat_id=ADMIN_ID[0],
                text=f"<b>💰 Заказ выполнен!</b>\n\n"
                     f"Покупка ID: {purchase_id}\n"
                     f"Пользователь: {purchase['username']}\n"
                     f"Товар: {purchase['amount']} Звёзд ⭐️\n"
                     f"Получатель: @{purchase['recipient_username']}\n"
                     f"Валюта: {purchase['currency']}\n"
                     f"Сумма: {purchase['price']:.2f}{bonus_msg}",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Purchase {purchase_id}: Failed to send admin notification: {str(e)}")

        # Начисление бонусов рефереру
        if purchase["user_id"]:
            referrer_id = await db.get_referrer_id(purchase["user_id"])
            if referrer_id:
                level_rewards = {1: 0.02, 2: 0.04, 3: 0.06, 4: 0.08, 5: 0.10}
                user = await db.get_user(purchase["user_id"])
                purchased_stars = purchase["amount"]
                
                if user["referrer_id"]:
                    referrer_id = user["referrer_id"]
                    referrer = await db.get_user(referrer_id)
                    if referrer:
                        current_level = referrer["referral_level"]
                        bonus_stars = purchased_stars * level_rewards[current_level]
                        total_referral_stars = await db.get_total_referral_stars(referrer_id) + purchased_stars
                        
                        # Обновляем звезды рефералов и проверяем переход на следующий уровень
                        new_level = min(5, (total_referral_stars // 5000) + 1)
                        await db.update_referral_level(referrer_id, new_level, total_referral_stars)
                        
                        # Начисляем бонусные звезды
                        await db.update_bonus_balance(referrer_id, bonus_stars)
                        try:
                            await bot.send_message(
                                referrer_id,
                                f"<b>🎁 Новые бонусы!</b>\n\n"
                                f"Ваш реферал @{user['username']} купил {purchased_stars} звёзд.\n"
                                f"Вам начислено {bonus_stars:.2f} бонусных звёзд (уровень {current_level}: {level_rewards[current_level]*100}%).\n"
                                f"{'🎉 Поздравляем! Уровень повышен до ' + str(new_level) + '!' if new_level > current_level else ''}",
                                parse_mode="HTML"
                            )
                        except Exception as e:
                            logging.error(f"Purchase {purchase_id}: Failed to send referral bonus notification to {referrer_id}: {str(e)}")

    except Exception as e:
        await db.update_purchase_status(purchase_id, "failed", error_message=str(e))
        await db.log_transaction(purchase_id, "processing_failed", "error", f"Ошибка: {str(e)}")
        logging.error(f"Purchase {purchase_id}: Failed - {str(e)}")
        # Отправляем уведомление об ошибке
        purchase = await db.get_purchase_by_id(str(purchase_id))
        if purchase and purchase["user_id"]:
            try:
                await bot.send_message(
                    chat_id=purchase["user_id"],
                    text=f"Покупка #{purchase_id} на {purchase['amount']} звезд не удалась: {str(e)}"
                )
            except Exception as e:
                logging.error(f"Purchase {purchase_id}: Failed to send error notification: {str(e)}")