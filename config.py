import aiohttp
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log'
)
logger = logging.getLogger(__name__)

async def get_star_prices() -> dict:
    """Получение текущей стоимости 1 звезды в TON и USDT, эквивалентной 1.38 RUB"""
    STAR_PRICE_RUB = 1.38  # Цена 1 звезды в RUB
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network,tether&vs_currencies=rub"
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Ошибка API CoinGecko: статус {response.status}")
                    return {"TON": 0.0057, "USDT": 0.017}  # Запасные значения
                data = await response.json()
                ton_rub = data.get("the-open-network", {}).get("rub", 0)
                usdt_rub = data.get("tether", {}).get("rub", 0)
                if ton_rub == 0 or usdt_rub == 0:
                    logger.error("Ошибка: нулевые курсы TON или USDT")
                    return {"TON": 0.01, "USDT": 0.012}  # Запасные значения
                return {
                    "TON": STAR_PRICE_RUB / ton_rub,  # Кол-во TON за 1.38 RUB
                    "USDT": STAR_PRICE_RUB / usdt_rub  # Кол-во USDT за 1.38 RUB
                }
    except Exception as e:
        logger.error(f"Ошибка при получении курсов через CoinGecko: {e}")
        return {"TON": 0.0057, "USDT": 0.017}  # Запасные значения при ошибке

MIN_STARS_AMOUNT = 50

DATABASE_PATH = "database.db"

FLASK_HOST = "http://localhost:5000"

CHAT_ID = -1002800830097 # ID канала для проверки подписки
CHANNEL_LINK = "https://t.me/+WKWn3RpfKKEwMWFi"  # линк на канал для доступа к боту
SUPPORT_URL = "https://t.me/HappySupportStars"  # линк ссылки поддержки
ADMIN_ID = ['1384040605']

STAR_PRICE_RUB = 1.69

FRAGMENT_STAR_PRICE_TON = 0.004188

SUPPORTED_CURRENCIES = ["USDT", "TON", "RUB"]