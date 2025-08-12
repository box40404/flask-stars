from fragment_integration import FragmentService
from database import Database
from aiocryptopay import AioCryptoPay, Networks
import logging
import os
from dotenv import load_dotenv
import asyncio
from aiogram import Bot
import threading

load_dotenv()

logging.basicConfig(filename="logs/site.log", level=logging.INFO)

def create_async_objects():
    """Создание новых асинхронных объектов для каждой операции."""
    crypto = AioCryptoPay(token=os.getenv("CRYPTO_TOKEN"), network=Networks.MAIN_NET)
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    db = Database()
    fragment_service = FragmentService()
    return crypto, bot, db, fragment_service

def run_in_new_loop(coro):
    """Запуск асинхронной функции в новом event loop в отдельном потоке."""
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()

async def check_invoice_status_async(purchase_id: int, invoice_id: str):
    """Проверка статуса инвойса каждые 2 секунды в течение 15 минут."""
    crypto, bot, db, fragment_service = create_async_objects()
    
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
                    await process_stars_purchase_async(purchase_id, invoice_id, crypto, bot, db, fragment_service)
                    return
                elif invoices[0].status in ["expired", "cancelled"]:
                    # Инвойс истек или отменен
                    await db.update_purchase_status(purchase_id, "cancelled", error_message=f"Invoice {invoices[0].status}")
                    await db.log_transaction(purchase_id, "invoice_failed", "error", f"Invoice {invoices[0].status}")
                    logging.error(f"Purchase {purchase_id}: Invoice {invoices[0].status}")
                    # Отправляем уведомление об отмене
                    purchase = await db.get_purchase_by_id(str(purchase_id))
                    if purchase and purchase.get("telegram_user_id"):
                        try:
                            await bot.send_message(
                                chat_id=purchase["telegram_user_id"],
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
                attempt += 1
                await asyncio.sleep(interval)

        # Если 15 минут истекли, отменяем покупку
        await db.update_purchase_status(purchase_id, "cancelled")
        try:
            await crypto.delete_invoice(invoice_id=int(invoice_id))
        except Exception as e:
            logging.error(f"Purchase {purchase_id}: Failed to delete invoice: {str(e)}")
        await db.log_transaction(purchase_id, "invoice_timeout", "error", "Invoice check timeout after 15 minutes")
        logging.warning(f"Purchase {purchase_id}: Invoice check timeout after {max_attempts} attempts")
        # Отправляем уведомление об отмене
        purchase = await db.get_purchase_by_id(str(purchase_id))
        if purchase and purchase.get("telegram_user_id"):
            try:
                await bot.send_message(
                    chat_id=purchase["telegram_user_id"],
                    text=f"Покупка #{purchase_id} на {purchase['amount']} звезд отменена: время ожидания оплаты (15 минут) истекло."
                )
            except Exception as e:
                logging.error(f"Purchase {purchase_id}: Failed to send timeout notification: {str(e)}")
    except Exception as e:
        await db.update_purchase_status(purchase_id, "failed", error_message=f"Unexpected error: {str(e)}")
        await db.log_transaction(purchase_id, "check_invoice_failed", "error", f"Unexpected error: {str(e)}")
        logging.warning(f"Purchase {purchase_id}: Check invoice failed - {str(e)}")
        # Отправляем уведомление об ошибке
        purchase = await db.get_purchase_by_id(str(purchase_id))
        if purchase and purchase.get("telegram_user_id"):
            try:
                await bot.send_message(
                    chat_id=purchase["telegram_user_id"],
                    text=f"Покупка #{purchase_id} на {purchase['amount']} звезд не удалась: {str(e)}"
                )
            except Exception as e:
                logging.error(f"Purchase {purchase_id}: Failed to send error notification: {str(e)}")

async def process_stars_purchase_async(purchase_id: int, invoice_id: str, crypto, bot, db, fragment_service):
    """Обработка покупки звезд после подтверждения оплаты."""
    try:
        purchase = await db.get_purchase_by_id(str(purchase_id))
        if not purchase:
            logging.error(f"Purchase {purchase_id}: Not found")
            return
        await db.log_transaction(purchase_id, "processing_started", "info", "Начата обработка заказа")
        logging.info(f"Purchase {purchase_id}: Started processing for {purchase['recipient_username']}")

        # Отправляем звезды через Fragment API
        result = await fragment_service.process_stars_purchase(purchase["amount"], purchase["recipient_username"])
        if result["success"]:
            await db.update_purchase_status(purchase_id, "completed", result.get("transaction_id"))
            await db.log_transaction(purchase_id, "stars_delivered", "success", f"Transaction ID: {result.get('transaction_id')}")
            logging.info(f"Purchase {purchase_id}: Stars delivered")
            # Отправляем уведомление об успехе
            if purchase.get("telegram_user_id"):
                try:
                    await bot.send_message(
                        chat_id=purchase["telegram_user_id"],
                        text=f"Покупка #{purchase_id} на {purchase['amount']} звезд успешно завершена! Звезды отправлены на {purchase['recipient_username']}."
                    )
                except Exception as e:
                    logging.error(f"Purchase {purchase_id}: Failed to send success notification: {str(e)}")
        else:
            await db.update_purchase_status(purchase_id, "failed", error_message=result["error"])
            await db.log_transaction(purchase_id, "delivery_failed", "error", f"Ошибка: {result['error']}")
            logging.error(f"Purchase {purchase_id}: Failed - {result['error']}")
            # Отправляем уведомление об ошибке
            if purchase.get("telegram_user_id"):
                try:
                    await bot.send_message(
                        chat_id=purchase["telegram_user_id"],
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
        if purchase and purchase.get("telegram_user_id"):
            try:
                await bot.send_message(
                    chat_id=purchase["telegram_user_id"],
                    text=f"Покупка #{purchase_id} на {purchase['amount']} звезд не удалась: {str(e)}"
                )
            except Exception as e:
                logging.error(f"Purchase {purchase_id}: Failed to send error notification: {str(e)}")

# Синхронные функции для вызова из Flask (сохраняем оригинальные имена)
def check_invoice_status(purchase_id: int, invoice_id: str):
    """Запуск проверки статуса инвойса (синхронная функция для вызова из Flask)."""
    run_in_new_loop(check_invoice_status_async(purchase_id, invoice_id))

def process_stars_purchase(purchase_id: int, invoice_id: str):
    """Запуск обработки покупки звезд (синхронная функция для вызова из Flask)."""
    crypto, bot, db, fragment_service = create_async_objects()
    run_in_new_loop(process_stars_purchase_async(purchase_id, invoice_id, crypto, bot, db, fragment_service))

