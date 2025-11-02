import io
import os
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # use non-interactive backend for servers
import matplotlib.pyplot as plt
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime

# --- Настройки ---
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

# --- Аналитика ---
def smart_money_flow(symbol, days=175):
    df = yf.download(symbol, period=f"{days}d", interval="1d", progress=False, auto_adjust=True)
    if df is None or len(df) < 20:
        return None
    # in case of multiindex columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
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
    ax.plot(df.index, df['Flow'], label="Smart Money Flow", linewidth=2)
    ax.axhline(85, color='red', linestyle='--', label='Sell Zone')
    ax.axhline(15, color='green', linestyle='--', label='Buy Zone')
    ax.axhline(50, color='gray', linestyle='-', alpha=0.5)
    ax.set_title(f"{symbol} — Smart Money Flow by Megatrend", fontsize=14, fontweight='bold')
    ax.set_ylim(0, 100)
    ax.legend()
    ax.grid(alpha=0.3)
    # annotate last value
    try:
        last_flow = float(df['Flow'].iloc[-1])
        last_date = df.index[-1]
        ax.text(last_date, last_flow, f"{last_flow:.1f}%", fontsize=10, fontweight='bold',
                ha='left', va='center', bbox=dict(facecolor='white', alpha=0.7, edgecolor='none'))
    except Exception:
        pass

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

    # Keep previous visual layout: grouped bars per asset
    fig = plt.figure(figsize=(19, 9))
    gs = fig.add_gridspec(1, 2, wspace=0.35)

    # 1) Current sentiment bar (last value)
    ax1 = fig.add_subplot(gs[0, 0])
    assets_list = list(flow_data.keys())
    scores = []
    for k in assets_list:
        try:
            scores.append(float(flow_data[k].iloc[-1]) / 100.0)
        except Exception:
            scores.append(0.0)

    bar_colors = []
    for s in scores:
        if s > 0.7:
            bar_colors.append('#006400')
        elif s > 0.55:
            bar_colors.append('#32CD32')
        elif s > 0.45:
            bar_colors.append('gray')
        elif s > 0.30:
            bar_colors.append('#FF8C00')
        else:
            bar_colors.append('#DC143C')

    bars = ax1.bar([a.upper() for a in assets_list], scores, color=bar_colors, edgecolor='black', linewidth=1.0)
    ax1.set_ylim(0, 1)
    ax1.set_ylabel('Sentiment (0-1)')
    ax1.set_title('Current Sentiment (CFTC, last trading day)', fontsize=12, fontweight='bold')
    ax1.grid(axis='y', alpha=0.3)
    ax1.tick_params(axis='x', rotation=15)

    for bar, score in zip(bars, scores):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                 f'{score*100:.1f}%', ha='center', va='bottom', fontweight='bold', fontsize=9)

    # 2) Distribution over 175 trading days (stacked-like grouped)
    ax2 = fig.add_subplot(gs[0, 1])
    colors = ['#006400', '#32CD32', 'gray', '#FF8C00', '#DC143C']
    level_ranges = [(70, 100), (55, 70), (45, 55), (30, 45), (0, 30)]
    level_names = ['Strong Bulls', 'Bulls', 'Neutral', 'Bears', 'Strong Bears']

    x = np.arange(len(assets_list))
    width = 0.15
    bottom = np.zeros(len(assets_list))

    # compute counts
    distribution_td = {asset: [0]*5 for asset in assets_list}
    for i, (low, high) in enumerate(level_ranges):
        values = []
        for asset in assets_list:
            series = flow_data[asset]
            cnt = int(((series > low) & (series <= high)).sum())
            values.append(cnt)
            distribution_td[asset][i] = cnt
        ax2.bar(x + i*width, values, width, bottom=bottom, color=colors[i], edgecolor='black')
        for j, td_count in enumerate(values):
            if td_count > 0:
                ax2.text(x[j] + i*width, bottom[j] + td_count/2, f'{td_count} d.', ha='center', va='center',
                         fontsize=8, color='black', fontweight='bold')
        bottom += np.array(values)

    ax2.set_xticks(x + width * 2)
    ax2.set_xticklabels([a.upper() for a in assets_list], fontsize=11)
    ax2.set_ylabel('Number of trading days')
    ax2.set_title('Distribution over 175 trading days', fontsize=12, fontweight='bold')
    ax2.set_ylim(0, 175)
    ax2.grid(axis='y', alpha=0.3)
    ax2.tick_params(axis='x', rotation=15)

    legend_elements = [plt.Line2D([0], [0], marker='s', color='w', markerfacecolor=colors[i], markersize=10, label=level_names[i])
                       for i in range(len(level_names))]
    ax2.legend(handles=legend_elements, fontsize=8, loc='center left', bbox_to_anchor=(1.02, 0.5))

    plt.suptitle('Sentiment: ' + ', '.join([a.upper() for a in assets_list]) + ' (CFTC, 175 Trading Days)\nby Megatrend',
                 fontsize=14, fontweight='bold', y=0.995)
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

# --- Telegram команды ---
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
    try:
        last_flow = float(df['Flow'].iloc[-1])
    except Exception:
        last_flow = None
    try:
        last_rsx = float(rsx.iloc[-1])
    except Exception:
        last_rsx = None

    buf = make_chart(df, asset.upper())
    await update.message.reply_photo(photo=buf)
    txt = f"{asset.upper()}:\n"
    if last_flow is not None:
        txt += f"Smart Money Flow: {last_flow:.1f}%\n"
    else:
        txt += "Smart Money Flow: n/a\n"
    if last_rsx is not None:
        txt += f"RSX(9): {last_rsx:.1f}\n"
    else:
        txt += "RSX(9): n/a\n"
    txt += f"Date: {df.index[-1].strftime('%d.%m.%Y')}"
    await update.message.reply_text(txt)

async def distribution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Generating distribution chart...")
    buf = make_distribution_chart()
    if buf:
        await update.message.reply_photo(photo=buf, caption="Smart Money Flow Distribution (175 Trading Days)")
    else:
        await update.message.reply_text("Could not generate distribution chart.")

async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Build and send all charts sequentially, then distribution."""
    await update.message.reply_text("Generating all charts (this may take a while)...")
    for cmd in FUTURES.keys():
        df = smart_money_flow(FUTURES[cmd])
        if df is None:
            await update.message.reply_text(f"{cmd.upper()}: not enough data.")
            continue
        buf = make_chart(df, cmd.upper())
        await update.message.reply_photo(photo=buf, caption=f"{cmd.upper()} — Smart Money Flow")
    # distribution
    bufd = make_distribution_chart()
    if bufd:
        await update.message.reply_photo(photo=bufd, caption="Smart Money Flow Distribution (175 Trading Days)")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = "Smart Money Flow by Megatrend — commands:\n"
    txt += "/gc /cl /pl /6e /6j /dx — charts\n"
    txt += "/dist — distribution\n"
    txt += "/all — all charts + distribution\n"
    await update.message.reply_text(txt)

# --- Создание Telegram приложения ---
if TOKEN == "ТВОЙ_ТОКЕН_СЮДА" or not TOKEN:
    print("WARNING: BOT_TOKEN is not set or left placeholder. Set BOT_TOKEN in Railway variables before deploy.")

app_bot = ApplicationBuilder().token(TOKEN).build()
for cmd in FUTURES.keys():
    app_bot.add_handler(CommandHandler(cmd, handle_asset))
app_bot.add_handler(CommandHandler("dist", distribution))
app_bot.add_handler(CommandHandler("all", all_command))
app_bot.add_handler(CommandHandler("start", start_cmd))

# --- Вебхуки ---
@app.route("/webhook", methods=["POST"])
def webhook():
    # receive update from Telegram and put into Application queue
    update = Update.de_json(request.get_json(force=True), app_bot.bot)
    app_bot.update_queue.put_nowait(update)
    return "OK", 200

@app.route("/")
def index():
    return "SmartMoney Bot is alive!", 200

# --- Запуск ---
if __name__ == "__main__":
    import asyncio
    async def run():
        # Устанавливаем webhook на правильный endpoint
        webhook_url = f"{URL}/webhook"
        try:
            ok = await app_bot.bot.set_webhook(webhook_url)
            print(f"set_webhook result: {ok} -> {webhook_url}")
        except Exception as e:
            print("Error setting webhook:", e)
        # Run flask (blocking). Railway will route HTTPS -> this flask server.
        app.run(host="0.0.0.0", port=PORT)

    asyncio.run(run())
