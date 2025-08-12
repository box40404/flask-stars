import aiosqlite
import logging
from datetime import datetime

logging.basicConfig(filename="logs/site.log", level=logging.INFO)

class Database:
    def __init__(self):
        self.db_name = "database.db"

    async def create_user(self, email: str, username: str, password: str = None):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                "INSERT INTO users (email, username, password, registration_date) VALUES (?, ?, ?, ?)",
                (email, username, password, datetime.utcnow().isoformat())
            )
            await db.commit()
            cursor = await db.execute("SELECT last_insert_rowid()")
            user_id = (await cursor.fetchone())[0]
            return user_id

    async def get_user(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("SELECT user_id, username, registration_date FROM users WHERE user_id = ?", (user_id,))
            return await cursor.fetchone()

    async def get_user_by_email(self, email: str):
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("SELECT user_id, username, password, registration_date FROM users WHERE email = ?", (email,))
            return await cursor.fetchone()

    async def get_bonus_balance(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("SELECT balance FROM bonus_balance WHERE user_id = ?", (user_id,))
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def create_purchase(self, user_id: int, item_type: str, amount: int, recipient_username: str, currency: str, price: float, invoice_id: str):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                """
                INSERT INTO purchases (user_id, product, amount, recipient_username, currency, price, invoice_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, item_type, amount, recipient_username, currency, price, invoice_id, "pending", datetime.utcnow().isoformat())
            )
            await db.commit()
            cursor = await db.execute("SELECT last_insert_rowid()")
            purchase_id = (await cursor.fetchone())[0]
            return purchase_id

    async def get_purchase_by_id(self, purchase_id: str):
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                "SELECT id, user_id, product, amount, recipient_username, currency, price, invoice_id, status, error_message FROM purchases WHERE id = ?",
                (purchase_id,)
            )
            row = await cursor.fetchone()
            if row:
                return {
                    "id": row[0], "user_id": row[1], "item_type": row[2], "amount": row[3],
                    "recipient_username": row[4], "currency": row[5], "price": row[6],
                    "invoice_id": row[7], "status": row[8], "error_message": row[9]
                }
            return None

    async def update_purchase_status(self, purchase_id: int, status: str, transaction_id: str = None, error_message: str = None):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                "UPDATE purchases SET status = ?, fragment_transaction_id = ?, error_message = ? WHERE id = ?",
                (status, transaction_id, error_message, purchase_id)
            )
            await db.commit()

    async def log_transaction(self, purchase_id: int, event: str, level: str, message: str):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                "INSERT INTO transaction_logs (purchase_id, action, status, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                (purchase_id, event, level, message, datetime.utcnow().isoformat())
            )
            await db.commit()
            logging.info(f"Transaction log: Purchase {purchase_id} - {event}: {message}")