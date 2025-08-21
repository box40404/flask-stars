import aiosqlite
import logging
from datetime import datetime, timedelta

logging.basicConfig(filename="logs/site.log", level=logging.INFO)

class Database:
    def __init__(self):
        self.db_name = "database.db"

    async def create_user(self, user_id: int, username: str, fullname: str, referrer_id: int = None) -> bool:
        """Добавление пользователя в базу данных"""
        try:
            msk_time = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    INSERT INTO users (user_id, username, fullname, registration_date, last_activity, referrer_id, referral_level)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, 1)
                """, (user_id, username, fullname, msk_time, referrer_id))
                await db.execute("""
                    INSERT INTO bonus_balance (user_id, balance)
                    VALUES (?, 0.0)
                """, (user_id,))
                await db.execute("""
                    INSERT INTO referral_levels (user_id, level, total_referral_stars)
                    VALUES (?, 1, 0)
                """, (user_id,))
                await db.commit()
                return True
        except Exception as e:
            return False

    async def get_user(self, user_id: int):
        """Получение информации о пользователе"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("""
                    SELECT u.*, r.level, r.total_referral_stars 
                    FROM users u 
                    LEFT JOIN referral_levels r ON u.user_id = r.user_id 
                    WHERE u.user_id = ?
                """, (user_id,))
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            return None

    async def get_bonus_balance(self, user_id: int):
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute("SELECT balance FROM bonus_balance WHERE user_id = ?", (user_id,))
            result = await cursor.fetchone()
            return result[0] if result else 0
        
    async def get_total_referral_stars(self, user_id: int) -> int:
        """Получить общее количество звезд, купленных рефералами"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                cursor = await db.execute("""
                    SELECT total_referral_stars FROM referral_levels WHERE user_id = ?
                """, (user_id,))
                row = await cursor.fetchone()
                return int(row[0]) if row else 0
        except Exception as e:
            return 0

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
        
    async def update_referral_level(self, user_id: int, level: int, total_referral_stars: int) -> bool:
        """Обновление уровня реферальной системы и количества звезд рефералов"""
        try:
            async with aiosqlite.connect(self.db_name) as db:
                await db.execute("""
                    INSERT OR REPLACE INTO referral_levels (user_id, level, total_referral_stars)
                    VALUES (?, ?, ?)
                """, (user_id, level, total_referral_stars))
                await db.execute("""
                    UPDATE users SET referral_level = ? WHERE user_id = ?
                """, (level, user_id))
                await db.commit()
                return True
        except Exception as e:
            return False

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
                (user_id, item_type, amount, recipient_username, currency, price, invoice_id, "pending", (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S"), (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S"), bonus_stars_used, bonus_discount)
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
                (status, transaction_id, error_message, (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S"), purchase_id)
            )
            await db.commit()

    async def verify_auth_token(self, token: str):
        """Проверить токен авторизации"""
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute(
                "SELECT user_id FROM auth_tokens WHERE token = ? AND expires_at > ?",
                (token, datetime.utcnow())
            )
            row = await cursor.fetchone()
            if row:
                user_id = row[0]
                # Удаляем токен после использования
                await db.execute("DELETE FROM auth_tokens WHERE token = ?", (token,))
                await db.commit()
                return user_id
            return None

    async def log_transaction(self, purchase_id: int, event: str, level: str, message: str):
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute(
                "INSERT INTO transaction_logs (purchase_id, action, status, details, timestamp) VALUES (?, ?, ?, ?, ?)",
                (purchase_id, event, level, message, (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S"))
            )
            await db.commit()
            logging.info(f"Transaction log: Purchase {purchase_id} - {event}: {message}")