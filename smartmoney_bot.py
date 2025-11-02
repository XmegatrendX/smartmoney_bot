from flask import Flask, request
import asyncio
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
import threading
import os

# === Настройки ===
TOKEN = os.getenv("BOT_TOKEN", "8104666804:AAEQoDrYxo6k7gTQknPbyAqYfCnZ1FVXy1s")
WEBHOOK_URL = "https://smartmoney-bot.up.railway.app/webhook"

# === Flask и aiogram ===
app = Flask(__name__)
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# === Команды бота ===
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Я SmartMoney Bot. Готов к работе!")

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("ℹ️ Команды:\n/start — начать\n/help — помощь")

@router.message()
async def echo_all(message: types.Message):
    await message.answer(f"Ты написал: {message.text}")

# === Flask маршруты ===
@app.route("/", methods=["GET"])
def index():
    return "✅ SmartMoney Bot Flask server is running", 200

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    try:
        update = types.Update(**request.json)
        asyncio.run(dp.feed_update(bot, update))
    except Exception as e:
        print("❌ Ошибка обработки апдейта:", e)
    return "ok", 200

# === Установка webhook ===
async def setup_webhook():
    await bot.delete_webhook()
    await bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook установлен: {WEBHOOK_URL}")

# === Flask сервер ===
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Flask сервер запущен на порту {port}")
    app.run(host="0.0.0.0", port=port)

# === Основной запуск ===
import threading
import asyncio

def main():
    """Запуск aiogram-бота в фоне (Flask управляется Gunicorn)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup_webhook())
    print("🚀 SmartMoney Bot готов к работе")
    loop.run_forever()

# Если Railway импортирует через gunicorn smartmoney_bot:app,
# Flask будет запущен Gunicorn'ом, а main() стартует фоном в отдельном потоке.
flask_thread = threading.Thread(target=main, daemon=True)
flask_thread.start()
