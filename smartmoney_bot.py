from flask import Flask, request
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
import asyncio
import os

TOKEN = os.getenv("BOT_TOKEN")  # Убедись, что в Railway переменная BOT_TOKEN задана
WEBHOOK_URL = "https://smartmoney-bot.up.railway.app/webhook"

app = Flask(__name__)

# --- Telegram bot setup ---
bot = Bot(token=TOKEN)
dp = Dispatcher()

@app.route("/", methods=["GET"])
def index():
    return "✅ SmartMoney Bot Flask server is running"

@app.route("/webhook", methods=["POST"])
async def webhook():
    try:
        update = Update.model_validate(request.json, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        print(f"Ошибка обработки webhook: {e}")
    return "OK", 200

async def on_startup():
    # Устанавливаем webhook для Telegram
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(WEBHOOK_URL)
        print(f"Webhook установлен на {WEBHOOK_URL}")
    else:
        print("Webhook уже установлен")

# --- Пример простого хендлера ---
@dp.message()
async def echo(message: types.Message):
    await message.answer(f"Привет, {message.from_user.first_name}! Я активен ✅")

if __name__ == "__main__":
    import threading

    def run_flask():
        app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

    threading.Thread(target=lambda: asyncio.run(on_startup())).start()
    run_flask()
