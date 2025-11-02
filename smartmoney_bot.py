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
import logging

# --- Логи для отладки ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Настройки ---
TOKEN = os.getenv("BOT_TOKEN", "ВСТАВЬ_СВОЙ_ТОКЕН_ЗДЕСЬ")  # ← Замени в Railway Variables
PORT = int(os.getenv("PORT", 8080))
URL = "https://smartmoney-bot.up.railway.app"  # ← Твой реальный URL

app = Flask(__name__)

# --- Активы ---
FUTURES = {
    'gc': 'GC=F',   # золото
    'cl': 'CL=F',   # нефть
    'pl': 'PL=F',   # платина
    '6e': '6E=F',   # евро
    '6j': '6J=F',   # иена
    'dx': 'DX=F'    # доллар
}

# --- Обработчик команд /gc, /cl и т.д. ---
async def handle_asset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        cmd = update.message.text.lower().lstrip("/")
        if cmd not in FUTURES:
            await update.message.reply_text("Неизвестный актив. Используй: /gc, /cl, /pl, /6e, /6j, /dx")
            return

        ticker = FUTURES[cmd]
        await update.message.reply_text(f"Загружаю данные по {ticker}...")

        data = yf.download(ticker, period="6mo", interval="1d", threads=True, progress=False)
        if data.empty:
            await update.message.reply_text("Не удалось получить данные. Попробуй позже.")
            return

        plt.figure(figsize=(8, 4))
        plt.plot(data["Close"], label=ticker, color='gold' if cmd == 'gc' else 'black')
        plt.title(f"{ticker} — последние 6 месяцев")
        plt.ylabel("Цена закрытия")
        plt.legend()
        plt.grid(True)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches='tight', dpi=100)
        buf.seek(0)
        plt.close()

        await update.message.reply_photo(
            photo=buf,
            caption=f"{ticker} — данные до {data.index[-1].strftime('%d.%m.%Y')}"
        )
        logger.info(f"График отправлен: {ticker}")
    except Exception as e:
        logger.error(f"Ошибка в handle_asset: {e}")
        await update.message.reply_text(f"Ошибка: {e}")

# --- Команды ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "SmartMoney Bot активен!\n"
        "Доступные команды:\n"
        "/gc — золото\n"
        "/cl — нефть\n"
        "/pl — платина\n"
        "/6e — евро\n"
        "/6j — иена\n"
        "/dx — доллар"
    )

async def dist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Распределение — в разработке.")

async def all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Команда /all — в разработке.")

# --- Telegram Bot ---
app_bot = ApplicationBuilder().token(TOKEN).build()

for cmd in FUTURES.keys():
    app_bot.add_handler(CommandHandler(cmd, handle_asset))

app_bot.add_handler(CommandHandler("start", start_cmd))
app_bot.add_handler(CommandHandler("dist", dist_cmd))
app_bot.add_handler(CommandHandler("all", all_cmd))

# --- Flask: КРИТИЧНО ВАЖНЫЙ МАРШРУТ ---
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        json_update = request.get_json(force=True)
        logger.info(f"Получен webhook: update_id={json_update.get('update_id')}")
        update = Update.de_json(json_update, app_bot.bot)
        
        # ФИКС: create_task вместо run
        asyncio.create_task(app_bot.process_update(update))
        
        return "OK", 200
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return f"Error: {e}", 500

@app.route("/")
def index():
    return "SmartMoney Bot работает! Webhook: /webhook", 200

# --- Установка Webhook ---
async def setup_webhook():
    webhook_url = f"{URL}/webhook"
    try:
        await app_bot.bot.delete_webhook()
        ok = await app_bot.bot.set_webhook(webhook_url)
        logger.info(f"Webhook установлен: {webhook_url} → {ok}")
    except Exception as e:
        logger.error(f"Ошибка установки webhook: {e}")

# --- Запуск ---
def run_flask():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    # Запуск Flask в отдельном потоке
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Asyncio цикл
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(setup_webhook())
    
    logger.info("SmartMoney Bot запущен на Railway")
    loop.run_forever()
