from flask import Flask, request
import asyncio
from aiogram import Bot, Dispatcher, types, Router
from aiogram.filters import Command
import threading
import time
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
def home():
    return "✅ SmartMoney Bot Flask server is running"

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        update_data = request.get_json(force=True)
        asyncio.run(process_update(update_data))
    except Exception as e:
        print("❌ Ошибка обработки апдейта:", e)
    return "ok", 200

async def process_update(update_data):
    update = types.Update(**update_data)
    await dp.feed_update(bot, update)

# === Установка webhook ===
async def setup_webhook():
    await bot.delete_webhook()
    success = await bot.set_webhook(WEBHOOK_URL)
    if success:
        print(f"✅ Webhook установлен: {WEBHOOK_URL}")
    else:
        print("⚠️ Ошибка установки вебхука!")

# === Flask сервер ===
def run_flask():
    app.run(host="0.0.0.0", port=8080)

# === Основной запуск ===
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    time.sleep(5)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup_webhook())

    print("🚀 SmartMoney Bot готов к работе")
    loop.run_forever()
