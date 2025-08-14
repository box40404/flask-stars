import aiosqlite
import logging
from datetime import datetime

logging.basicConfig(filename="logs/site.log", level=logging.INFO)

class Database:
    def __init__(self):
        self.db_name = "database.db"

    async def get_user(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                "SELECT user_id, username, fullname, registration_date, is_subscribed, last_activity, referrer_id FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                return {
                    "user_id": row[0], "username": row[1], "fullname": row[2], "registration_date": row[3],
                    "is_subscribed": row[4], "last_activity": row[5], "referrer_id": row[6]
                }
            return None

    async def get_bonus_balance(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("SELECT balance FROM bonus_balance WHERE user_id = ?", (user_id,))
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def update_bonus_balance(self, user_id: int, amount: float):
        async with aiosqlite.connect(self.db_name) as db:
            current_balance = await self.get_bonus_balance(user_id)
            new_balance = max(0, current_balance + amount)  # Не допускаем отрицательный баланс
            await db.execute(
                "INSERT OR REPLACE INTO bonus_balance (user_id, balance) VALUES (?, ?)",
                (user_id, new_balance)
            )
            await db.commit()
            return new_balance

    async def get_referrer_id(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("SELECT referrer_id FROM users WHERE user_id = ?", (user_id,))
            result = await cursor.fetchone()
            return result[0] if result and result[0] else None

    async def create_purchase(self, user_id: int, item_type: str, amount: int, recipient_username: str, currency: str, price: float, invoice_id: str, bonus_stars_used: float = 0.0, bonus_discount: float = 0.0):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                """
                INSERT INTO purchases (user_id, product, amount, recipient_username, currency, price, invoice_id, status, created_at, updated_at, bonus_stars_used, bonus_discount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, item_type, amount, recipient_username, currency, price, invoice_id, "pending", datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), bonus_stars_used, bonus_discount)
            )
            await db.commit()
            cursor = await db.execute("SELECT last_insert_rowid()")
            purchase_id = (await cursor.fetchone())[0]
            return purchase_id

    async def get_purchase_by_id(self, purchase_id: str):
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                """
                SELECT id, user_id, product, amount, recipient_username, currency, price, invoice_id, status,
                       created_at, updated_at, fragment_transaction_id, error_message, bonus_stars_used, bonus_discount
                FROM purchases WHERE id = ?
                """,
                (purchase_id,)
            )
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0], "user_id": row[1], "product": row[2], "amount": row[3],
                    "recipient_username": row[4], "currency": row[5], "price": row[6],
                    "invoice_id": row[7], "status": row[8], "created_at": row[9],
                    "updated_at": row[10], "fragment_transaction_id": row[11], "error_message": row[12],
                    "bonus_stars_used": row[13], "bonus_discount": row[14]
                }
            return None

    async def update_purchase_status(self, purchase_id: int, status: str, transaction_id: str = None, error_message: str = None):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                "UPDATE purchases SET status = ?, fragment_transaction_id = ?, error_message = ?, updated_at = ? WHERE id = ?",
                (status, transaction_id, error_message, datetime.utcnow(), purchase_id)
            )
            await db.commit()

    async def log_transaction(self, purchase_id: int, event: str, level: str, message: str):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                "INSERT INTO transaction_logs (purchase_id, action, status, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                (purchase_id, event, level, message, datetime.utcnow())
            )
            await db.commit()
            logging.info(f"Transaction log: Purchase {purchase_id} - {event}: {message}")