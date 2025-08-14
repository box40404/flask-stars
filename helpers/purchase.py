from quart import current_app
import logging
import asyncio
from config import ADMIN_ID, get_star_prices

logging.basicConfig(filename="logs/site.log", level=logging.INFO)

async def check_invoice_status(purchase_id: int, invoice_id: str):
    """Проверка статуса инвойса каждые 2 секунды в течение 15 минут."""
    crypto = current_app.config["CRYPTO"]
    bot = current_app.config["BOT"]
    db = current_app.config["DB"]
    fragment_service = current_app.config["FRAGMENT"]
    
    try:
        max_duration = 15 * 60  # 15 минут в секундах
        interval = 2  # Интервал проверки: 2 секунды
        max_attempts = max_duration // interval
        attempt = 1

        while attempt <= max_attempts:
            try:
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
                    purchase = await db.get_purchase_by_id(str(purchase_id))
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

async def process_stars_purchase(purchase_id: int, invoice_id: str):
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
                     f"Пользователь: {purchase['user_id']}\n"
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
                bonus_amount = int(purchase["amount"] * 0.1)  # 10% от суммы покупки
                await db.update_bonus_balance(referrer_id, bonus_amount)
                await db.log_transaction(purchase_id, "referral_bonus", "info", f"Referrer {referrer_id} received {bonus_amount} bonuses")
                logging.info(f"Purchase {purchase_id}: Referrer {referrer_id} received {bonus_amount} bonuses")
                try:
                    await bot.send_message(
                        chat_id=referrer_id,
                        text=f"Ваш реферал @{purchase['recipient_username']} совершил покупку на {purchase['amount']} звезд! Вам начислено {bonus_amount} бонусов."
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