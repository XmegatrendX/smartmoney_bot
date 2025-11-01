import io
import os
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext import ApplicationBuilder

TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_СЮДА")
PORT = int(os.getenv("PORT", 8080))
URL = os.getenv("RAILWAY_URL", "https://smartmoney-bot.up.railway.app")

app = Flask(__name__)

FUTURES = {
    'gc': 'GC=F',
    'cl': 'CL=F',
    'pl': 'PL=F',
    '6e': '6E=F',
    '6j': '6J=F',
    'dx': 'DX=F'
}

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

def make_chart(df, symbol):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(df.index, df['Flow'], label="Smart Money Flow", color='navy', linewidth=2)
    ax.axhline(85, color='red', linestyle='--', label='Sell Zone')
    ax.axhline(15, color='green', linestyle='--', label='Buy Zone')
    ax.axhline(50, color='gray', linestyle='-', alpha=0.5)
    ax.set_title(f"{symbol} — Smart Money Flow", fontsize=14, fontweight='bold')
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(alpha=0.3)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

def make_distribution_chart():
    assets = list(FUTURES.keys())
    flow_data = {}
    for a in assets:
        df = smart_money_flow(FUTURES[a])
        if df is not None:
            flow_data[a] = df['Flow']
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
        for asset, series in flow_data.items():
            cnt = ((series > low) & (series <= high)).sum()
            counts.append(cnt)
        ax.bar(x + i*width, counts, width, label=level_names[i], color=colors[i], edgecolor='black')
    ax.set_xticks(x + width * 2)
    ax.set_xticklabels([a.upper() for a in flow_data.keys()])
    ax.set_ylabel("Trading Days")
    ax.set_title("Distribution (175 Trading Days)", fontsize=13, fontweight='bold')
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=0.3)
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

async def handle_asset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    asset = update.message.text.replace('/', '').lower()
    if asset not in FUTURES:
        await update.message.reply_text("Unknown command.")
        return
    await update.message.reply_text(f"Fetching {asset.upper()} data...")
    df = smart_money_flow(FUTURES[asset])
    if df is None:
        await update.message.reply_text("Not enough data.")
        return
    rsx = calculate_rsx(df['Close'])
    last_flow = float(df['Flow'].iloc[-1])
    last_rsx = float(rsx.iloc[-1])
    buf = make_chart(df, asset.upper())
    await update.message.reply_photo(photo=buf)
    await update.message.reply_text(
        f"{asset.upper()}:\nSmart Money Flow: {last_flow:.1f}%\nRSX(9): {last_rsx:.1f}"
    )

async def distribution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Generating distribution chart...")
    buf = make_distribution_chart()
    if buf:
        await update.message.reply_photo(photo=buf, caption="Smart Money Flow Distribution")

app_bot = ApplicationBuilder().token(TOKEN).build()
for cmd in FUTURES.keys():
    app_bot.add_handler(CommandHandler(cmd, handle_asset))
app_bot.add_handler(CommandHandler("dist", distribution))

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), app_bot.bot)
    app_bot.update_queue.put_nowait(update)
    return "ok"

@app.route("/")
def index():
    return "SmartMoney Bot running!"

if __name__ == "__main__":
    import asyncio
    async def run():
        await app_bot.bot.set_webhook(f"{URL}/{TOKEN}")
        app.run(host="0.0.0.0", port=PORT)
    asyncio.run(run())
