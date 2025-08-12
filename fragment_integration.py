import asyncio
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from fragment_api_lib.client import FragmentAPIClient
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()

@dataclass
class FragmentResult:
    """Результат операции с Fragment"""
    success: bool
    transaction_id: Optional[str] = None
    message: str = ""
    error: Optional[str] = None

class FragmentIntegration:
    """
    Интеграция с Fragment.com через fragment-api-lib
    
    Требует:
    - Установка библиотеки: pip install fragment-api-lib==1.0.1
    - Настройка переменных окружения: FRAGMENT_SEED, FRAGMENT_COOKIES
    """
    
    def __init__(self):
        self.seed = os.getenv("FRAGMENT_SEED")
        self.cookies = os.getenv("FRAGMENT_COOKIES")
        self.is_configured = bool(self.seed)
        self.client = FragmentAPIClient()
        
        if not self.is_configured:
            print("WARNING: Fragment API не настроен. Проверьте FRAGMENT_SEED в .env")
    
    async def buy_stars(self, amount: int, recipient_username: str) -> FragmentResult:
        """
        Покупка звезд через Fragment API
        
        Args:
            amount: Количество звезд
            recipient_username: Username получателя
            
        Returns:
            FragmentResult: Результат операции
        """
        print("INFO: Покупка", amount, "звезд для @", recipient_username)
        
        if not self.is_configured:
            print("ERROR: Fragment API не настроен. Покупка невозможна.")
            return FragmentResult(
                success=False,
                error="API не настроен: отсутствуют FRAGMENT_SEED или FRAGMENT_COOKIES",
                message=f"Не удалось купить {amount} звезд для @{recipient_username}"
            )
        
        try:
            result = self.client.buy_stars_without_kyc(
                username=recipient_username,
                amount=amount,
                seed=self.seed
            )
            
            # Проверяем, содержит ли результат ошибку
            if result.get("error") or not result.get("success", True):
                error_message = result.get("error", "Неизвестная ошибка API")
                print("ERROR: Ошибка API при покупке звезд:", error_message)
                return FragmentResult(
                    success=False,
                    error=error_message,
                    message=f"Не удалось купить {amount} звезд для @{recipient_username}"
                )
            
            transaction_id = result.get("transaction_id", f"fragment_{amount}_{recipient_username}_{int(asyncio.get_event_loop().time())}")
            
            return FragmentResult(
                success=True,
                transaction_id=transaction_id,
                message=f"Успешно отправлено {amount} звезд пользователю @{recipient_username}"
            )
            
        except ValueError as e:
            print("ERROR: Ошибка значения при покупке звезд:", str(e))
            return FragmentResult(
                success=False,
                error=str(e),
                message=f"Не удалось купить {amount} звезд для @{recipient_username}"
            )
        except RuntimeError as e:
            print("ERROR: Ошибка выполнения при покупке звезд:", str(e))
            return FragmentResult(
                success=False,
                error=str(e),
                message=f"Не удалось купить {amount} звезд для @{recipient_username}"
            )
        except Exception as e:
            print("ERROR: Неизвестная ошибка при покупке звезд:", str(e))
            return FragmentResult(
                success=False,
                error=str(e),
                message=f"Не удалось купить {amount} звезд для @{recipient_username}"
            )
    
    async def check_transaction_status(self, transaction_id: str) -> str:
        """
        Проверка статуса транзакции
        
        Args:
            transaction_id: ID транзакции
            
        Returns:
            str: Статус транзакции (pending, completed, failed)
        """
        print("INFO: Проверка статуса транзакции", transaction_id)
        
        if not self.is_configured:
            print("ERROR: Fragment API не настроен. Проверка статуса невозможна.")
            return "failed"
        
        try:
            # Примечание: fragment-api-lib v1.0.1 не предоставляет явного метода для проверки статуса.
            # Предполагаем, что успешная транзакция имеет статус completed.
            # Для реальной проверки обратитесь к @JailBroken для уточнения API.
            return "completed"
            
        except Exception as e:
            print("ERROR: Ошибка при проверке статуса транзакции", transaction_id, ":", str(e))
            return "failed"
    
    async def get_balance(self) -> float:
        """
        Получение баланса аккаунта
        
        Returns:
            float: Баланс в TON
        """
        print("INFO: Получение баланса аккаунта")
        
        if not self.is_configured:
            print("ERROR: Fragment API не настроен. Возвращается нулевой баланс.")
            return 0.0
        
        try:
            result = self.client.get_balance(seed=self.seed)
            
            # Проверяем, содержит ли результат ошибку
            if result.get("error") or not result.get("success", True):
                error_message = result.get("error", "Неизвестная ошибка API")
                print("ERROR: Ошибка API при получении баланса:", error_message)
                return 0.0
                
            balance = float(result.get("balance", 0.0))
            return balance
            
        except ValueError as e:
            print("ERROR: Ошибка значения при получении баланса:", str(e))
            return 0.0
        except RuntimeError as e:
            print("ERROR: Ошибка выполнения при получении баланса:", str(e))
            return 0.0
        except Exception as e:
            print("ERROR: Неизвестная ошибка при получении баланса:", str(e))
            return 0.0

class FragmentService:
    """Сервис для работы с Fragment"""
    
    def __init__(self):
        self.integration = FragmentIntegration()
    
    async def process_stars_purchase(self, amount: int, recipient_username: str) -> Dict[str, Any]:
        """
        Обработка покупки звезд
        
        Args:
            amount: Количество звезд
            recipient_username: Username получателя
            
        Returns:
            Dict: Результат обработки
        """
        try:
            # Проверяем баланс
            balance = await self.integration.get_balance()
            print("INFO: Баланс аккаунта:", balance, "TON")
            
            # Покупаем звезды
            #result = await self.integration.buy_stars(amount, recipient_username)
            result = FragmentResult(
                success=True,
                transaction_id='test_id',
                message=f"Успешно test {amount} звезд пользователю @{recipient_username}"
            )
            
            return {
                "success": result.success,
                "transaction_id": result.transaction_id,
                "message": result.message,
                "error": result.error
            }
            
        except Exception as e:
            print("ERROR: Ошибка при обработке покупки звезд:", str(e))
            return {
                "success": False,
                "error": str(e),
                "message": "Произошла ошибка при обработке заказа"
            }