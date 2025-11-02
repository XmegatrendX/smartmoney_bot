import io
import os
import yfinance as yf
import matplotlib.pyplot as plt
from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import Dispatcher, CommandHandler, CallbackContext
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Настройки ---
TOKEN = os.getenv("BOT_TOKEN")
URL = "https://smartmoney-bot.up.railway.app"

app = FastAPI()
bot = Bot(TOKEN)
dispatcher = Dispatcher(bot, None, workers=0, use_context=True)

FUTURES = {
    'gc': 'GC=F', 'cl': 'CL=F', 'pl': 'PL=F',
    '6e': '6E=F', '6j': '6J=F', 'dx': 'DX=F'
}

# --- Команды ---
def handle_asset(update: Update, context: CallbackContext):
    cmd = update.message.text.lower().lstrip("/")
    if cmd not in FUTURES:
        update.message.reply_text("Используй: /gc, /cl, /pl, /6e, /6j, /dx")
        return

    ticker = FUTURES[cmd]
    update.message.reply_text(f"Загружаю {ticker}...")

    try:
        data = yf.download(ticker, period="6mo", progress=False)
        if data.empty:
            update.message.reply_text("Нет данных.")
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

        # Указываем filename и mime_type вручную
        update.message.reply_photo(
            photo=buf,
            filename="chart.png",
            caption=f"{ticker} — до {data.index[-1].strftime('%d.%m.%Y')}"
        )
    except Exception as e:
        update.message.reply_text(f"Ошибка: {e}")
        logger.error(f"Ошибка в handle_asset: {e}")

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "SmartMoney Bot готов!\n"
        "Команды: /gc, /cl, /pl, /6e, /6j, /dx"
    )

# Добавляем команды
dispatcher.add_handler(CommandHandler("start", start))
for cmd in FUTURES:
    dispatcher.add_handler(CommandHandler(cmd, handle_asset))

# --- Webhook ---
@app.post("/webhook")
async def webhook(request: Request):
    try:
        json_update = await request.json()
        update = Update.de_json(json_update, bot)
        if update:
            dispatcher.process_update(update)
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
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(f"{URL}/webhook")
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
