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

# --- Telegram Bot ---
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

    try:
        data = yf.download(ticker, period="6mo", progress=False)
        if data.empty:
            await update.message.reply_text("Нет данных.")
            return

        plt.figure(figsize=(10, 6))
        plt.plot(data["Close"], label=ticker, color='gold' if cmd == 'gc' else 'black')
        plt.title(f"{ticker} — 6 месяцев")
        plt.ylabel("Цена")
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        buf.seek(0)
        plt.close()

        await update.message.reply_photo(
            photo=buf,
            caption=f"{ticker} — до {data.index[-1].strftime('%d.%m.%Y')}"
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "SmartMoney Bot готов!\n"
        "Команды: /gc, /cl, /pl, /6e, /6j, /dx"
    )

# Добавляем команды
for cmd in FUTURES:
    bot_app.add_handler(CommandHandler(cmd, handle_asset))
bot_app.add_handler(CommandHandler("start", start))

# --- Webhook ---
@app.post("/webhook")
async def webhook(request: Request):
    try:
        json_update = await request.json()
        update = Update.de_json(json_update, bot_app.bot)
        if update:
            await bot_app.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return {"error": str(e)}, 500

@app.get("/")
async def root():
    return {"status": "SmartMoney Bot жив!", "webhook": f"{URL}/webhook"}

# --- Установка webhook при старте ---
@app.on_event("startup")
async def startup():
    try:
        await bot_app.bot.delete_webhook()
        await bot_app.bot.set_webhook(f"{URL}/webhook")
        logger.info(f"Webhook установлен: {URL}/webhook")
    except Exception as e:
        logger.error(f"Ошибка webhook: {e}")

# --- Запуск ---
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info"
    )
