from quart import Quart
from routes.web import web
from routes.api import api
from aiocryptopay import AioCryptoPay, Networks
from aiogram import Bot
from database import Database
from fragment_integration import FragmentService
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()

app = Quart(__name__, template_folder="templates", static_folder="static")

# Создаем глобальные экземпляры
app.config["CRYPTO"] = AioCryptoPay(token=os.getenv("CRYPTO_TOKEN"), network=Networks.MAIN_NET)
app.config["BOT"] = Bot(token=os.getenv("BOT_TOKEN"))
app.config["DB"] = Database()
app.config["FRAGMENT"] = FragmentService()

# Регистрация blueprint'ов
app.register_blueprint(web)
app.register_blueprint(api, url_prefix="/api")

# Закрытие ресурсов при завершении приложения
@app.after_serving
async def shutdown():
    await app.config["CRYPTO"].close()
    await app.config["BOT"].session.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)