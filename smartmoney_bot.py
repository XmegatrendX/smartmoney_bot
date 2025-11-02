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
        await update.message.reply_text(f"📈 Загружаю данные по {ticker}...")

        data = yf.download(ticker, period="6mo", interval="1d", threads=True, progress=False)
        if data.empty:
            await update.message.reply_text("⚠️ Не удалось получить данные. Попробуй позже.")
            logger.error(f"Пустые данные для {ticker}")
            return

        plt.figure(figsize=(10, 6))
        plt.plot(data["Close"], label=ticker, linewidth=2)
        plt.title(f"{ticker} — Цена закрытия (6 месяцев)")
        plt.ylabel("Цена ($)")
        plt.xlabel("Дата")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches='tight', dpi=100)
        buf.seek(0)
        plt.close()

        last_date = data.index[-1].strftime('%d.%m.%Y')
        last_price = data["Close"].iloc[-1]
        
        await update.message.reply_photo(
            photo=buf,
            caption=f"📊 {ticker}\n💰 Последняя цена: ${last_price:.2f}\n📅 Данные до: {last_date}"
        )
        logger.info(f"✅ График отправлен: {ticker}")
    except Exception as e:
        logger.error(f"❌ Ошибка в handle_asset: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")

# --- Команды ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *SmartMoney Bot* активен!\n\n"
        "📈 Доступные активы:\n"
        "• `/gc` — Золото (Gold)\n"
        "• `/cl` — Нефть WTI\n"
        "• `/pl` — Платина\n"
        "• `/6e` — Евро (EUR/USD)\n"
        "• `/6j` — Японская иена\n"
        "• `/dx` — Долларовый индекс\n\n"
        "💡 *Пример:* `/gc` — график золота за 6 месяцев",
        parse_mode="Markdown"
    )

async def dist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Распределение активов — в разработке.")

async def all_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📦 Все активы сразу — в разработке.")

# --- Telegram Bot ---
app_bot = ApplicationBuilder().token(TOKEN).build()

# Добавляем обработчики команд
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
        update_id = json_update.get('update_id', 'unknown')
        logger.info(f"📨 Получен webhook: update_id={update_id}")
        
        update = Update.de_json(json_update, app_bot.bot)
        if update:
            # ✅ КРИТИЧНЫЙ ФИКС: create_task вместо run
            asyncio.create_task(app_bot.process_update(update))
            logger.info(f"✅ Обработка update_id={update_id} запущена")
        else:
            logger.error(f"❌ Не удалось распарсить update_id={update_id}")
        
        return "OK", 200
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return f"Error: {e}", 500

@app.route("/")
def index():
    return f"""
    <h1>🤖 SmartMoney Bot</h1>
    <p>Webhook: <code>{URL}/webhook</code></p>
    <p>Статус: <b>🟢 Активен</b></p>
    <p>Токен: <code>{TOKEN[:10]}...</code></p>
    """, 200

@app.route("/health")
def health():
    return "OK", 200

# --- Установка Webhook ---
async def setup_webhook():
    webhook_url = f"{URL}/webhook"
    try:
        # Удаляем старый webhook
        await app_bot.bot.delete_webhook()
        logger.info("🧹 Старый webhook удалён")
        
        # Устанавливаем новый
        ok = await app_bot.bot.set_webhook(webhook_url)
        logger.info(f"✅ Webhook установлен: {webhook_url} → {ok}")
        
        # Проверяем статус
        info = await app_bot.bot.get_webhook_info()
        logger.info(f"📊 Webhook info: pending={info.pending_update_count}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")

# --- Запуск ---
def run_flask():
    logger.info("🚀 Запуск Flask сервера...")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    # Запуск Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Asyncio цикл для Telegram
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    logger.info("🔄 Настройка webhook...")
    loop.run_until_complete(setup_webhook())
    
    logger.info("🎉 SmartMoney Bot запущен на Railway!")
    logger.info(f"📍 Webhook: {URL}/webhook")
    logger.info(f"🌐 Сервер: http://0.0.0.0:{PORT}")
    
    # Держим цикл живым
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("🛑 Остановка бота...")
        loop.close()
