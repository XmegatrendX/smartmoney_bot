import io
import os
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime
import threading
import asyncio

# --- Настройки ---
TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_СЮДА")
PORT = int(os.getenv("PORT", 8080))
URL = os.getenv("RAILWAY_URL", "https://smartmoney-bot.up.railway.app")

app = Flask(__name__)

FUTURES = {
    'gc': 'GC=F',   # золото
    'cl': 'CL=F',   # нефть
    'pl': 'PL=F',   # платина
    '6e': '6E=F',   # евро
    '6j': '6J=F',   # иена
    'dx': 'DX=F'    # долларовый индекс
}

# --- Обработчик активов ---
async def handle_asset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет график выбранного фьючерса по команде (/gc, /cl, ...)"""
    try:
        cmd = update.message.text.lower().replace("/", "")
        if cmd not in FUTURES:
            await update.message.reply_text("Неизвестный актив. Используй: /gc, /cl, /pl, /6e, /6j, /dx")
            return

        ticker = FUTURES[cmd]
        await update.message.reply_text(f"📈 Загружаю данные по {ticker}...")

        data = yf.download(ticker, period="6mo", interval="1d")
        if data.empty:
            await update.message.reply_text("⚠️ Не удалось получить данные.")
            return

        plt.figure(figsize=(8, 4))
        plt.plot(data["Close"], label=ticker)
        plt.title(f"{ticker} — последние 6 месяцев")
        plt.legend()
        plt.grid(True)

        buf = io.BytesIO()
        plt.savefig(buf, format="png")
        buf.seek(0)
        plt.close()

        await update.message.reply_photo(photo=buf)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
        print("handle_asset error:", e)

# --- Остальные команды (заглушки) ---
async def distribution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Distribution report (пока пусто).")

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📦 Команда /all пока не реализована.")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 SmartMoney Bot активен. Доступные команды: /gc, /cl, /pl, /6e, /6j, /dx")

# --- Telegram приложение ---
app_bot = ApplicationBuilder().token(TOKEN).build()

for cmd in FUTURES.keys():
    app_bot.add_handler(CommandHandler(cmd, handle_asset))

app_bot.add_handler(CommandHandler("dist", distribution))
app_bot.add_handler(CommandHandler("all", all_command))
app_bot.add_handler(CommandHandler("start", start_cmd))

# --- Flask маршруты ---
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        json_update = request.get_json(force=True)
        update = Update.de_json(json_update, app_bot.bot)
        asyncio.get_event_loop().create_task(app_bot.process_update(update))
    except Exception as e:
        print("Webhook error:", e)
    return "OK", 200

@app.route("/")
def index():
    return "SmartMoney Bot is alive!", 200

# --- Запуск ---
async def setup_webhook():
    webhook_url = f"{URL}/webhook"
    try:
        await app_bot.bot.delete_webhook()
        ok = await app_bot.bot.set_webhook(webhook_url)
        print(f"✅ Webhook set to {webhook_url} (result: {ok})")
    except Exception as e:
        print("❌ Error setting webhook:", e)

def run_flask():
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    # Flask в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()

    # Асинхронно запустить webhook и polling loop
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setup_webhook())
    print("🚀 SmartMoney Bot started on Railway")
    loop.run_forever()
