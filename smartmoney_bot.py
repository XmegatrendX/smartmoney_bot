import io
import os
import yfinance as yf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import threading
import asyncio
import logging  # Логи для отладки

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Настройки ---
TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_СЮДА")  # Проверь в Railway Variables
PORT = int(os.getenv("PORT", 8080))
URL = "https://smartmoney-bot.up.railway.app"  # Жёсткий URL (из твоих логов)

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
    try:
        cmd = update.message.text.lower().replace("/", "")
        if cmd not in FUTURES:
            await update.message.reply_text("Неизвестный актив. Используй: /gc, /cl, /pl, /6e, /6j, /dx")
            return

        ticker = FUTURES[cmd]
        await update.message.reply_text(f"📈 Загружаю данные по {ticker}...")

        data = yf.download(ticker, period="6mo", interval="1d", threads=True, progress=False)
        if data.empty:
            await update.message.reply_text("⚠️ Не удалось получить данные (проверь позже).")
            return

        plt.figure(figsize=(8, 4))
        plt.plot(data["Close"], label=ticker)
        plt.title(f"{ticker} — последние 6 месяцев")
        plt.ylabel("Close Price")
        plt.legend()
        plt.grid(True)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches='tight')
        buf.seek(0)
        plt.close()

        await update.message.reply_photo(photo=buf, caption=f"Данные до {data.index[-1].strftime('%d.%m.%Y')}")
    except Exception as e:
        logger.error(f"Ошибка в handle_asset: {e}")
        await update.message.reply_text(f"Ошибка: {e}")

# --- Остальные команды ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 SmartMoney Bot активен. Доступные команды: /gc, /cl, /pl, /6e, /6j, /dx")

async def distribution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Distribution report (пока пусто).")

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📦 Команда /all пока не реализована.")

# --- Telegram приложение ---
app_bot = ApplicationBuilder().token(TOKEN).build()

for cmd in FUTURES.keys():
    app_bot.add_handler(CommandHandler(cmd, handle_asset))

app_bot.add_handler(CommandHandler("start", start_cmd))
app_bot.add_handler(CommandHandler("dist", distribution))
app_bot.add_handler(CommandHandler("all", all_command))

# --- Flask маршруты ---
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        json_update = request.get_json(force=True)
        logger.info(f"✅ Webhook получен: update_id = {json_update.get('update_id', 'unknown')}")
        update = Update.de_json(json_update, app_bot.bot)
        
        # ✅ ФИКС: create_task вместо run — не блокирует Flask
        asyncio.create_task(app_bot.process_update(update))
        
        return "OK", 200
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return f"Error: {e}", 500

@app.route("/")
def index():
    return f"SmartMoney Bot is alive! Webhook: {URL}/webhook", 200

# --- Установка вебхука ---
async def setup_webhook():
    webhook_url = f"{URL}/webhook"
    try:
        await app_bot.bot.delete_webhook()
        ok = await app_bot.bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook set to {webhook_url} (result: {ok})")
    except Exception as e:
        logger.error(f"❌ Error setting webhook: {e}")

# --- Запуск ---
def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup_webhook())
    
    logger.info("🚀 SmartMoney Bot started on Railway")
    loop.run_forever()
