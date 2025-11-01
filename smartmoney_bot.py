import os
import io
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# === Настройки ===
TOKEN = os.getenv("BOT_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_URL")  # например https://smartmoney-production.up.railway.app

FUTURES = {
    'gc': 'GC=F',
    'cl': 'CL=F',
    'pl': 'PL=F',
    '6e': '6E=F',
    '6j': '6J=F',
    'dx': 'DX=F'
}

# === SMART MONEY FLOW ===
def smart_money_flow(symbol, days=175):
    df = yf.download(symbol, period=f"{days}d", interval="1d", progress=False, auto_adjust=True)
    if len(df) < 20:
        return None
    df['Vol_Z'] = (df['Volume'] - df['Volume'].rolling(20).mean()) / (df['Volume'].rolling(20).std() + 1e-8)
    df['Price_Acc'] = df['Close'].pct_change().diff().fillna(0)
    df['Signal'] = 0.8 * df['Vol_Z'] + 0.2 * df['Price_Acc']
    df['Flow'] = (df['Signal'].clip(-3, 3) * 16.67 + 50).ewm(span=3).mean()
    return df

def calculate_rsx(close, period=9):
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1/period).mean()
    down = (-delta).clip(lower=0).ewm(alpha=1/period).mean()
    rs = up / (down + 1e-8)
    return 100 - (100 / (1 + rs))

# === ГРАФИК SMART MONEY FLOW ===
def make_chart(df, symbol):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(df.index, df['Flow'], label="Smart Money Flow", color='navy', linewidth=2)
    ax.axhline(85, color='red', linestyle='--', label='Sell Zone')
    ax.axhline(15, color='green', linestyle='--', label='Buy Zone')
    ax.axhline(50, color='gray', linestyle='-', alpha=0.5)
    ax.set_title(f"{symbol} — Smart Money Flow by Megatrend", fontsize=14, fontweight='bold')
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(alpha=0.3)

    last_flow = float(df['Flow'].iloc[-1])
    ax.text(df.index[-1], last_flow, f"{last_flow:.1f}%", color='navy',
            fontsize=10, fontweight='bold', ha='left', va='center',
            bbox=dict(facecolor='white', alpha=0.7, edgecolor='navy'))

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

# === ДИАГРАММА DISTRIBUTION ===
def make_distribution_chart():
    flow_data = {}
    for a, ticker in FUTURES.items():
        df = smart_money_flow(ticker)
        if df is not None:
            flow_data[a.upper()] = df['Flow']

    if not flow_data:
        return None

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ['#006400', '#32CD32', 'gray', '#FF8C00', '#DC143C']
    level_ranges = [(70, 100), (55, 70), (45, 55), (30, 45), (0, 30)]
    level_names = ['Strong Bulls', 'Bulls', 'Neutral', 'Bears', 'Strong Bears']

    x = np.arange(len(flow_data))
    width = 0.15

    for i, (low, high) in enumerate(level_ranges):
        counts = []
        for series in flow_data.values():
            cnt = ((series > low) & (series <= high)).sum()
            counts.append(cnt)
        ax.bar(x + i * width, counts, width, label=level_names[i], color=colors[i], edgecolor='black')

    ax.set_xticks(x + width * 2)
    ax.set_xticklabels(flow_data.keys())
    ax.set_ylabel("Trading Days")
    ax.set_title("Distribution (175 Trading Days) — Smart Money Flow by Megatrend", fontsize=13, fontweight='bold')
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=0.3)

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

# === TELEGRAM КОМАНДЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Smart Money Flow by Megatrend*\n\n"
        "Используй команды:\n"
        "/GC — Gold\n"
        "/CL — WTI Crude Oil\n"
        "/PL — Platinum\n"
        "/6E — Euro\n"
        "/6J — Yen\n"
        "/DX — Dollar Index\n"
        "/dist — Distribution chart\n"
        "/all — Все графики подряд\n",
        parse_mode="Markdown"
    )

async def handle_asset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = update.message.text.replace('/', '').lower()
    if asset not in FUTURES:
        await update.message.reply_text("❌ Unknown command. Try /GC or /CL")
        return

    symbol = FUTURES[asset]
    await update.message.reply_text(f"📊 Fetching {asset.upper()} data...")

    df = smart_money_flow(symbol)
    if df is None:
        await update.message.reply_text("⚠️ Not enough data.")
        return

    rsx = calculate_rsx(df['Close'])
    last_flow = float(df['Flow'].iloc[-1])
    last_rsx = float(rsx.iloc[-1])

    buf = make_chart(df, asset.upper())
    await update.message.reply_photo(photo=buf)
    await update.message.reply_text(
        f"📈 *{asset.upper()}*\n"
        f"Smart Money Flow: *{last_flow:.1f}%*\n"
        f"RSX(9): *{last_rsx:.1f}*\n"
        f"Date: {df.index[-1].strftime('%d.%m.%Y')}",
        parse_mode='Markdown'
    )

async def distribution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Generating distribution chart...")
    buf = make_distribution_chart()
    if buf:
        await update.message.reply_photo(photo=buf, caption="📊 Smart Money Flow Distribution (175 Trading Days)")
    else:
        await update.message.reply_text("⚠️ Could not generate distribution chart.")

async def all_charts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Building all Smart Money Flow charts...")
    for cmd, ticker in FUTURES.items():
        df = smart_money_flow(ticker)
        if df is None:
            continue
        rsx = calculate_rsx(df['Close'])
        last_flow = float(df['Flow'].iloc[-1])
        last_rsx = float(rsx.iloc[-1])
        buf = make_chart(df, cmd.upper())
        await update.message.reply_photo(photo=buf, caption=f"{cmd.upper()} — Flow {last_flow:.1f}% | RSX {last_rsx:.1f}")
    buf = make_distribution_chart()
    if buf:
        await update.message.reply_photo(photo=buf, caption="📊 Distribution (175 Days)")

# === Flask-приложение и Webhook ===
flask_app = Flask(__name__)
bot_app = Application.builder().token(TOKEN).build()

bot_app.add_handler(CommandHandler("start", start))
for cmd in FUTURES.keys():
    bot_app.add_handler(CommandHandler(cmd, handle_asset))
bot_app.add_handler(CommandHandler("dist", distribution))
bot_app.add_handler(CommandHandler("all", all_charts))

@flask_app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    bot_app.update_queue.put_nowait(update)
    return "ok", 200

if __name__ == "__main__":
    import asyncio
    import logging
    logging.basicConfig(level=logging.INFO)

    asyncio.get_event_loop().run_until_complete(
        bot_app.bot.set_webhook(f"{RAILWAY_URL}/{TOKEN}")
    )

    print("✅ Bot is running: Smart Money Flow by Megatrend (Webhook mode)")
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
