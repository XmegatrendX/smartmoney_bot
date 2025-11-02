import io
import os
import yfinance as yf
import matplotlib.pyplot as plt
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Настройки ---
TOKEN = os.getenv("BOT_TOKEN")
URL = "https://smartmoney-bot.up.railway.app"

app = FastAPI()
bot_app = ApplicationBuilder().token(TOKEN).build()

FUTURES = {
    'gc': 'GC=F', 'cl': 'CL=F', 'pl': 'PL=F',
    '6e': '6E=F', '6j': '6J=F', 'dx': 'DX=F'
}

# --- Команды ---
async def handle_asset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.lower().lstrip("/")
    if cmd not in FUTURES:
        await update.message.reply_text("Используй: /gc, /cl, /pl, /6e, /6j, /dx")
        return

    ticker = FUTURES[cmd]
    await update.message.reply_text(f"Загружаю {ticker}...")

    data = yf.download(ticker, period="6mo", progress=False)
    if data.empty:
        await update.message.reply_text("Нет данных.")
        return

    plt.figure(figsize=(10, 6))
    plt.plot(data["Close"], label=ticker)
    plt.title(f"{ticker} — 6 месяцев")
    plt.grid(True)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close()

    await update.message.reply_photo(buf, caption=f"{ticker} до {data.index[-1].date()}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("SmartMoney Bot готов! Используй /gc")

for cmd in FUTURES:
    bot_app.add_handler(CommandHandler(cmd, handle_asset))
bot_app.add_handler(CommandHandler("start", start))

# --- Webhook ---
@app.post("/webhook")
async def webhook(request: Request):
    json_update = await request.json()
    update = Update.de_json(json_update, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "SmartMoney Bot жив!"}

# --- Установка webhook ---
async def setup():
    await bot_app.bot.delete_webhook()
    await bot_app.bot.set_webhook(f"{URL}/webhook")
    logger.info(f"Webhook установлен: {URL}/webhook")

# --- Запуск ---
import uvicorn

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_completed(setup())
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
