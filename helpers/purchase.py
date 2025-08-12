from quart import current_app
import logging
import asyncio
from config import ADMIN_ID

logging.basicConfig(filename="logs/site.log", level=logging.INFO)

async def check_invoice_status(purchase_id: int, invoice_id: str):
    """Проверка статуса инвойса каждые 2 секунды в течение 15 минут."""
    crypto = current_app.config["CRYPTO"]
    bot = current_app.config["BOT"]
    db = current_app.config["DB"]
    fragment_service = current_app.config["FRAGMENT"]
    
    try:
        max_duration = 1 * 60  # 15 минут в секундах
        interval = 2  # Интервал проверки: 2 секунды
        max_attempts = max_duration // interval
        attempt = 1

        while attempt <= max_attempts:
            try:
                invoices = await crypto.get_invoices(invoice_ids=[int(invoice_id)])
                
                if invoices[0].status == "paid":
                    # Инвойс оплачен, запускаем обработку покупки
                    await process_stars_purchase(purchase_id, invoice_id, crypto, bot, db, fragment_service)
                    return
                elif invoices[0].status in ["expired", "cancelled"]:
                    # Инвойс истек или отменен
                    await db.update_purchase_status(purchase_id, "cancelled", error_message=f"Invoice {invoices[0].status}")
                    await db.log_transaction(purchase_id, "invoice_failed", "error", f"Invoice {invoices[0].status}")
                    logging.error(f"Purchase {purchase_id}: Invoice {invoices[0].status}")
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
        await crypto.delete_invoice(invoice_id=int(invoice_id))
        logging.info(f"Purchase {purchase_id}: Invoice check timeout after {max_attempts} attempts")
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
        await db.update_purchase_status(purchase_id, "failed", error_message=f"Unexpected error: {str(e)}")
        await crypto.delete_invoice(invoice_id=int(invoice_id))
        await db.log_transaction(purchase_id, "check_invoice_failed", "error", f"Unexpected error: {str(e)}")
        logging.error(f"Purchase {purchase_id}: Check invoice failed - {str(e)}")
        # Отправляем уведомление об ошибке
        purchase = await db.get_purchase_by_id(str(purchase_id))
        if purchase and purchase.get("user_id"):
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID[0],
                    text=f"Покупка #{purchase_id} на {purchase['amount']} звезд не удалась: {str(e)}"
                )
            except Exception as e:
                logging.error(f"Purchase {purchase_id}: Failed to send error notification: {str(e)}")

async def process_stars_purchase(purchase_id: int, invoice_id: str, crypto, bot, db, fragment_service):
    """Обработка покупки звезд после подтверждения оплаты."""
    try:
        purchase = await db.get_purchase_by_id(str(purchase_id))
        if not purchase:
            logging.error(f"Purchase {purchase_id}: Not found")
            return
        await db.log_transaction(purchase_id, "processing_started", "info", f"Начата обработка заказа для {purchase['recipient_username']}")
        logging.info(f"Purchase {purchase_id}: Started processing for {purchase['recipient_username']}")

        # Отправляем звезды через Fragment API
        result = await fragment_service.process_stars_purchase(purchase["amount"], purchase["recipient_username"])
        if result["success"]:
            await db.update_purchase_status(purchase_id, "completed", result.get("transaction_id"))
            await db.log_transaction(purchase_id, "stars_delivered", "success", f"Transaction ID: {result.get('transaction_id')}")
            logging.info(f"Purchase {purchase_id}: Stars delivered")
            # Отправляем уведомление об успехе
            if purchase.get("user_id"):
                try:
                    await bot.send_message(
                        chat_id=purchase["user_id"],
                        text=f"Покупка #{purchase_id} на {purchase['amount']} звезд успешно завершена! Звезды отправлены на {purchase['recipient_username']}."
                    )
                except Exception as e:
                    logging.error(f"Purchase {purchase_id}: Failed to send success notification: {str(e)}")
        else:
            await db.update_purchase_status(purchase_id, "failed", error_message=result["error"])
            await db.log_transaction(purchase_id, "delivery_failed", "error", f"Ошибка: {result['error']}")
            logging.error(f"Purchase {purchase_id}: Failed - {result['error']}")
            # Отправляем уведомление об ошибке
            if purchase.get("user_id"):
                try:
                    await bot.send_message(
                        chat_id=ADMIN_ID[0],
                        text=f"Покупка #{purchase_id} на {purchase['amount']} звезд не удалась: {result['error']}"
                    )
                except Exception as e:
                    logging.error(f"Purchase {purchase_id}: Failed to send failure notification: {str(e)}")
    except Exception as e:
        await db.update_purchase_status(purchase_id, "failed", error_message=str(e))
        await db.log_transaction(purchase_id, "processing_failed", "error", f"Ошибка: {str(e)}")
        logging.error(f"Purchase {purchase_id}: Failed - {str(e)}")
        # Отправляем уведомление об ошибке
        purchase = await db.get_purchase_by_id(str(purchase_id))
        if purchase and purchase.get("user_id"):
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID[0],
                    text=f"Покупка #{purchase_id} на {purchase['amount']} звезд не удалась: {str(e)}"
                )
            except Exception as e:
                logging.error(f"Purchase {purchase_id}: Failed to send error notification: {str(e)}")