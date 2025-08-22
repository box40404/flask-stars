import aiohttp
import logging
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='logs/site.log'
)
logger = logging.getLogger(__name__)

_star_prices_cache = {
    "prices": {"TON": 0.0057, "USDT": 0.017},  # Запасные значения по умолчанию
    "last_updated": None  # Время последнего обновления
}
CACHE_TTL = 300  # Время жизни кэша в секундах (5 минут)

async def get_star_prices() -> dict:
    """Получение текущей стоимости 1 звезды в TON и USDT, эквивалентной 1.38 RUB"""
    STAR_PRICE_RUB = 1.38  # Цена 1 звезды в RUB
    current_time = datetime.utcnow()

    # Проверяем, есть ли актуальный кэш
    if (
        _star_prices_cache["last_updated"]
        and (current_time - _star_prices_cache["last_updated"]).total_seconds() < CACHE_TTL
    ):
        logger.info("Возвращены кэшированные цены звезд")
        return _star_prices_cache["prices"]

    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network,tether&vs_currencies=rub"
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Ошибка API CoinGecko: статус {response.status}")
                    return _star_prices_cache["prices"]  # Возвращаем кэш при ошибке
                data = await response.json()
                ton_rub = data.get("the-open-network", {}).get("rub", 0)
                usdt_rub = data.get("tether", {}).get("rub", 0)
                if ton_rub == 0 or usdt_rub == 0:
                    logger.error("Ошибка: нулевые курсы TON или USDT")
                    return _star_prices_cache["prices"]  # Возвращаем кэш при ошибке
                prices = {
                    "TON": STAR_PRICE_RUB / ton_rub,  # Кол-во TON за 1.38 RUB
                    "USDT": STAR_PRICE_RUB / usdt_rub  # Кол-во USDT за 1.38 RUB
                }
                # Обновляем кэш
                _star_prices_cache["prices"] = prices
                _star_prices_cache["last_updated"] = current_time
                logger.info("Цены звезд успешно обновлены и закэшированы")
                return prices
    except Exception as e:
        logger.error(f"Ошибка при получении курсов через CoinGecko: {e}")
        return _star_prices_cache["prices"]  # Возвращаем кэш при ошибке

MIN_STARS_AMOUNT = 50

DATABASE_PATH = "database.db"

CHAT_ID = -1002800830097 # ID канала для проверки подписки
CHANNEL_LINK = "https://t.me/+WKWn3RpfKKEwMWFi"  # линк на канал для доступа к боту
SUPPORT_URL = "https://t.me/HappySupportStars"  # линк ссылки поддержки
ADMIN_ID = ['1384040605']

TON_WALLET_ADDRESS = '0QCzH0vnl-glR5XORGbJ3DCCXVMn_vBbEd6RS2InrWupf7OD'
TONCENTER_API_KEY = os.getenv("TONCENTER_API_KEY")

STAR_PRICE_RUB = 1.69

FRAGMENT_STAR_PRICE_TON = 0.004188

SUPPORTED_CURRENCIES = ["USDT", "TON", "RUB"]