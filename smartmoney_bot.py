from flask import Flask, request
import asyncio
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
import os

# === Настройки ===
TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_БОТА")
WEBHOOK_URL = "https://smartmoney-bot.up.railway.app/webhook"

# === Инициализация ===
app = Flask(__name__)
bot = Bot(token=TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# === Команды ===
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
    return "✅ SmartMoney Bot Flask server is running"

@app.route("/webhook", methods=["POST"])
def webhook():
    # Flask синхронный, aiogram — асинхронный → нужно через asyncio
    try:
        update_data = request.get_json()
        update = types.Update(**update_data)
        asyncio.run(dp.feed_update(bot, update))
    except Exception as e:
        print("❌ Ошибка при обработке апдейта:", e)
        return "error", 500
    return "ok", 200

# === Запуск сервера ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🚀 Flask сервер запущен на порту {port}")
    app.run(host="0.0.0.0", port=port)
