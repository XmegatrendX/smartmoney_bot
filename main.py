import io
import os
import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Настройки ---
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is not set!")

URL     = "https://smartmoney-bot-ilqm.onrender.com"
CHAT_ID = int(os.getenv("CHAT_ID", "0"))   # задать в env переменных Render

# --- Telegram Bot ---
bot_app = ApplicationBuilder().token(TOKEN).build()

FUTURES = {
    'gc': 'GC=F', 'cl': 'CL=F', 'pl': 'PL=F',
    '6e': '6E=F', '6j': '6J=F', 'dx': 'DX=F'
}


# ────────────────────────────────────────────────
# Лунные перигеи
# ────────────────────────────────────────────────
def get_lunar_perigees(days_back: int = 175) -> list:
    """Возвращает даты перигеев за последние days_back дней + один следующий."""
    try:
        import ephem
    except ImportError:
        return []
    perigees  = []
    start     = ephem.Date(datetime.now() - pd.Timedelta(days=days_back + 30))
    end       = ephem.Date(datetime.now() + pd.Timedelta(days=35))
    moon      = ephem.Moon()
    cutoff    = pd.Timestamp(datetime.now() - pd.Timedelta(days=days_back))
    now_ts    = pd.Timestamp(datetime.now())
    date      = start
    prev_dist = None
    prev_date = None
    while date < end:
        moon.compute(date)
        dist = moon.earth_distance
        if prev_dist is not None and prev_dist < dist:
            # Тернарный поиск минимума — точнее бинарного
            lo, hi = prev_date, date
            for _ in range(30):
                m1 = lo + (hi - lo) / 3
                m2 = lo + (hi - lo) * 2 / 3
                moon.compute(m1); d1 = moon.earth_distance
                moon.compute(m2); d2 = moon.earth_distance
                if d1 < d2:
                    hi = m2
                else:
                    lo = m1
            perigee = (lo + hi) / 2
            p = pd.Timestamp(ephem.Date(perigee).datetime())
            # Защита от дублей: минимум 20 дней между перигеями
            if (not perigees or (p - perigees[-1]).days > 20) and p >= cutoff:
                perigees.append(p)
                if p > now_ts:
                    break  # нашли следующий — хватит
        prev_dist = dist
        prev_date = date
        date += 0.5  # шаг 0.5 дня
    return perigees


# ────────────────────────────────────────────────
# Smart Money Flow
# ────────────────────────────────────────────────
def smart_money_flow(symbol, days=175):
    df = yf.download(symbol, period=f"{days}d", interval="1d", progress=False, auto_adjust=True)
    if df is None or len(df) < 20:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    # 1. Percentile rank вместо z-score (0..100, устойчив к выбросам)
    df['Vol_Pct'] = df['Volume'].rolling(20).apply(
        lambda x: (x[:-1] < x[-1]).sum() / (len(x) - 1) * 100, raw=True
    )

    # 2. Vol_Trend — нарастает ли участие за последние 5 дней (0..100)
    raw_trend       = df['Volume'].rolling(5).mean() / (df['Volume'].rolling(20).mean() + 1e-8) - 1
    df['Vol_Trend'] = (raw_trend.clip(-1, 1) + 1) * 50

    # 3. Price_Acc — ускорение цены (0..100)
    raw_acc         = df['Close'].pct_change().diff().fillna(0)
    df['Price_Acc'] = (raw_acc.clip(-0.03, 0.03) / 0.03 + 1) * 50

    # Итоговый сигнал (все компоненты в 0..100)
    df['Signal'] = (
        0.7 * df['Vol_Pct'] +
        0.2 * df['Vol_Trend'] +
        0.1 * df['Price_Acc']
    ).fillna(50)

    # 4. Адаптивный span: активный рынок → span=3, тихий → span=10
    vol_std   = df['Volume'].rolling(20).std() / (df['Volume'].rolling(20).mean() + 1e-8)
    span_vals = (3 + (1 - vol_std.clip(0, 1)) * 7).fillna(5).round().astype(int).values
    sig_vals  = df['Signal'].values
    result    = np.zeros(len(sig_vals))
    result[0] = sig_vals[0]
    for i in range(1, len(sig_vals)):
        alpha     = 2.0 / (span_vals[i] + 1.0)
        result[i] = alpha * sig_vals[i] + (1 - alpha) * result[i - 1]

    df['Flow'] = result
    return df


# ────────────────────────────────────────────────
# RSX Джурика
# ────────────────────────────────────────────────
def calculate_rsx(series: pd.Series, length: int = 9) -> pd.Series:
    src = series.values.astype(float)
    n   = len(src)
    rsx = np.zeros(n)
    f8  = np.zeros(n); f10 = np.zeros(n); v8 = np.zeros(n)
    f18 = 3.0 / (length + 2.0); f20 = 1.0 - f18
    f28 = np.zeros(n); f30 = np.zeros(n)
    f38 = np.zeros(n); f40 = np.zeros(n)
    f48 = np.zeros(n); f50 = np.zeros(n)
    f58 = np.zeros(n); f60 = np.zeros(n)
    f68 = np.zeros(n); f70 = np.zeros(n)
    f78 = np.zeros(n); f80 = np.zeros(n)
    f88 = np.zeros(n); f90 = np.zeros(n)

    for i in range(n):
        f8[i]  = 100.0 * src[i]
        f10[i] = f8[i - 1] if i > 0 else 0.0
        v8[i]  = f8[i] - f10[i]
        f28[i] = f20 * (f28[i-1] if i > 0 else 0.0) + f18 * v8[i]
        f30[i] = f18 * f28[i] + f20 * (f30[i-1] if i > 0 else 0.0)
        vC     = f28[i] * 1.5 - f30[i] * 0.5
        f38[i] = f20 * (f38[i-1] if i > 0 else 0.0) + f18 * vC
        f40[i] = f18 * f38[i] + f20 * (f40[i-1] if i > 0 else 0.0)
        v10    = f38[i] * 1.5 - f40[i] * 0.5
        f48[i] = f20 * (f48[i-1] if i > 0 else 0.0) + f18 * v10
        f50[i] = f18 * f48[i] + f20 * (f50[i-1] if i > 0 else 0.0)
        v14    = f48[i] * 1.5 - f50[i] * 0.5
        f58[i] = f20 * (f58[i-1] if i > 0 else 0.0) + f18 * abs(v8[i])
        f60[i] = f18 * f58[i] + f20 * (f60[i-1] if i > 0 else 0.0)
        v18    = f58[i] * 1.5 - f60[i] * 0.5
        f68[i] = f20 * (f68[i-1] if i > 0 else 0.0) + f18 * v18
        f70[i] = f18 * f68[i] + f20 * (f70[i-1] if i > 0 else 0.0)
        v1C    = f68[i] * 1.5 - f70[i] * 0.5
        f78[i] = f20 * (f78[i-1] if i > 0 else 0.0) + f18 * v1C
        f80[i] = f18 * f78[i] + f20 * (f80[i-1] if i > 0 else 0.0)
        v20    = f78[i] * 1.5 - f80[i] * 0.5
        f88[i] = length - 1 if (i > 0 and f90[i-1] == 0 and length - 1 >= 5) else 5
        f90[i] = (
            1 if i == 0 or f90[i-1] == 0
            else f88[i] + 1 if f88[i] <= f90[i-1]
            else f90[i-1] + 1
        )
        f0     = 1 if (f88[i] >= f90[i] and f8[i] != f10[i]) else 0
        if f88[i] == f90[i] and f0 == 0:
            f90[i] = 0
        v4     = (v14 / v20 + 1.0) * 50.0 if (f88[i] < f90[i] and abs(v20) > 1e-8) else 50.0
        rsx[i] = max(0.0, min(100.0, v4))

    return pd.Series(rsx, index=series.index)


# ────────────────────────────────────────────────
# График: Flow + RSX подграфик
# ────────────────────────────────────────────────
def make_chart(df, symbol):
    rsx      = calculate_rsx(df['Flow'], length=9)
    perigees = get_lunar_perigees(175)
    now_ts   = pd.Timestamp(datetime.now())

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(12, 8),
        gridspec_kw={'height_ratios': [2, 1]},
        sharex=True
    )
    fig.subplots_adjust(hspace=0.05)

    # ── Volume Stress / Participation Index ──
    ax1.plot(df.index, df['Flow'], label="Participation Index", linewidth=2, color='navy')
    ax1.axhline(85, color='red',   linestyle='--', linewidth=1, label='Overbought (85)')
    ax1.axhline(15, color='green', linestyle='--', linewidth=1, label='Oversold (15)')
    ax1.axhline(50, color='gray',  linestyle='-',  alpha=0.4)
    ax1.fill_between(df.index, 85, df['Flow'].clip(lower=85), alpha=0.15, color='red')
    ax1.fill_between(df.index, df['Flow'].clip(upper=15), 15, alpha=0.15, color='blue')

    # Лунные перигеи на ax1
    for p in perigees:
        if p <= now_ts:
            ax1.axvline(p, color='red', linestyle='--', linewidth=0.8, alpha=0.5)
        else:
            ax1.axvline(p, color='red', linestyle='--', linewidth=1.2, alpha=0.9)
            ax1.text(p, 92, f"↓ {p.strftime('%d.%m')}", color='red',
                     fontsize=7, ha='center',
                     bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='red', alpha=0.8))
            break  # только один следующий

    ax1.set_title(f"{symbol} — Volume Stress / Participation Index", fontsize=14, fontweight='bold')
    ax1.set_ylim(0, 100)
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(alpha=0.3)

    # аннотация последнего значения
    try:
        last_flow = float(df['Flow'].iloc[-1])
        last_date = df.index[-1]
        ax1.annotate(
            f"{last_date.strftime('%d.%m.%Y')}\n{last_flow:.1f}%",
            xy=(last_date, last_flow),
            xytext=(-60, 15), textcoords='offset points',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.8),
            fontsize=9, fontweight='bold',
        )
    except Exception:
        pass

    # ── RSX(9) ──
    ax2.plot(df.index, rsx, label="RSX(9)", linewidth=1.5, color='orange')
    ax2.axhline(70, color='red',   linestyle='--', linewidth=1)
    ax2.axhline(30, color='green', linestyle='--', linewidth=1)

    # Лунные перигеи на ax2
    for p in perigees:
        if p <= now_ts:
            ax2.axvline(p, color='red', linestyle='--', linewidth=0.8, alpha=0.5)
        else:
            ax2.axvline(p, color='red', linestyle='--', linewidth=1.2, alpha=0.9)
            break  # только один следующий

    ax2.set_ylim(0, 100)
    ax2.set_ylabel('RSX(9)', fontsize=9)
    ax2.legend(loc='upper left', fontsize=9)
    ax2.grid(alpha=0.3)

    # аннотация последнего RSX
    try:
        last_rsx  = float(rsx.iloc[-1])
        last_date = rsx.index[-1]
        peak_idx  = rsx.idxmax()
        peak_val  = float(rsx.loc[peak_idx])
        ax2.annotate(
            f"{peak_idx.strftime('%d.%m.%Y')}\nRSX: {peak_val:.1f}",
            xy=(peak_idx, peak_val),
            xytext=(10, -20), textcoords='offset points',
            bbox=dict(boxstyle='round,pad=0.3', facecolor='lightblue', alpha=0.8),
            fontsize=9,
        )
    except Exception:
        pass

    # ── Легенда фаз рынка ──
    phases = [
        ("Accumulation", "Накопление",   "Сжатие, тихий рынок, скрытое участие",          "20–45, волатильность низкая",            "#4169E1"),
        ("Expansion",    "Расширение",   "Резкий рост участия, вход объёма",               "Прорыв выше 55–60, быстрый наклон вверх","#228B22"),
        ("Trend",        "Тренд/Удерж.", "Участие стабильно высокое",                      "65–85, держится выше 60",                "#006400"),
        ("Distribution", "Распределение","Индекс высокий, но цена теряет импульс",         "70–90, RSX ↓ или дивергенция",           "#FF8C00"),
        ("Collapse",     "Сброс/Капит.", "Агрессивный выход объёма вниз",                  "Резкое падение ниже 40, ускорение вниз", "#DC143C"),
    ]

    # добавляем третий подграфик только для таблицы
    ax_table = fig.add_axes([0.01, -0.22, 0.98, 0.20])
    ax_table.axis('off')

    col_labels = ["Фаза", "Рус. название", "Что происходит", "Показания индекса"]
    col_widths = [0.10, 0.13, 0.46, 0.31]
    row_h = 0.16
    header_y = 0.92

    # заголовки
    x = 0.0
    for label, w in zip(col_labels, col_widths):
        ax_table.text(x + w/2, header_y, label,
                      ha='center', va='center', fontsize=7.5, fontweight='bold',
                      transform=ax_table.transAxes,
                      bbox=dict(boxstyle='square,pad=0.3', fc='#2c2c2c', ec='none'))
        ax_table.text(x + w/2, header_y, label,
                      ha='center', va='center', fontsize=7.5, fontweight='bold',
                      color='white', transform=ax_table.transAxes)
        x += w

    # строки
    for row_i, (eng, rus, what, index_val, color) in enumerate(phases):
        y = header_y - (row_i + 1) * row_h
        row_data = [eng, rus, what, index_val]
        x = 0.0
        bg = '#f9f9f9' if row_i % 2 == 0 else '#ffffff'
        for col_i, (val, w) in enumerate(zip(row_data, col_widths)):
            ax_table.add_patch(plt.Rectangle((x, y - row_h*0.45), w, row_h*0.9,
                                             transform=ax_table.transAxes,
                                             fc=bg, ec='#cccccc', linewidth=0.5,
                                             clip_on=False))
            # цветной маркер в первой колонке
            if col_i == 0:
                ax_table.add_patch(plt.Rectangle((x, y - row_h*0.45), 0.004, row_h*0.9,
                                                 transform=ax_table.transAxes,
                                                 fc=color, ec='none', clip_on=False))
            ax_table.text(x + w/2, y, val,
                          ha='center', va='center', fontsize=7,
                          transform=ax_table.transAxes, color='#111111')
            x += w

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf


# ────────────────────────────────────────────────
# График распределения
# ────────────────────────────────────────────────
def make_distribution_chart():
    assets = list(FUTURES.keys())
    flow_data = {}
    for a in assets:
        df = smart_money_flow(FUTURES[a])
        if df is not None:
            flow_data[a] = df['Flow']
    if not flow_data:
        return None

    fig = plt.figure(figsize=(19, 9))
    gs  = fig.add_gridspec(1, 2, wspace=0.35)

    ax1 = fig.add_subplot(gs[0, 0])
    assets_list = list(flow_data.keys())
    scores = [float(flow_data[k].iloc[-1]) / 100.0 if len(flow_data[k]) > 0 else 0.0 for k in assets_list]
    bar_colors = [
        '#006400' if s > 0.7 else
        '#32CD32' if s > 0.55 else
        'gray'    if s > 0.45 else
        '#FF8C00' if s > 0.30 else
        '#DC143C'
        for s in scores
    ]
    bars = ax1.bar([a.upper() for a in assets_list], scores, color=bar_colors, edgecolor='black', linewidth=1.0)
    ax1.set_ylim(0, 1)
    ax1.set_ylabel('Sentiment (0-1)')
    ax1.set_title('Current Sentiment (CFTC, last trading day)', fontsize=12, fontweight='bold')
    ax1.grid(axis='y', alpha=0.3)
    for bar, score in zip(bars, scores):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                 f'{score*100:.1f}%', ha='center', va='bottom', fontweight='bold', fontsize=9)

    ax2 = fig.add_subplot(gs[0, 1])
    colors       = ['#006400', '#32CD32', 'gray', '#FF8C00', '#DC143C']
    level_ranges = [(70, 100), (55, 70), (45, 55), (30, 45), (0, 30)]
    level_names  = ['Strong Bulls', 'Bulls', 'Neutral', 'Bears', 'Strong Bears']
    x     = np.arange(len(assets_list))
    width = 0.15

    for i, (low, high) in enumerate(level_ranges):
        bottom = np.zeros(len(assets_list))
        values = np.array([
            int(((flow_data[asset] > low) & (flow_data[asset] <= high)).sum())
            for asset in assets_list
        ])
        ax2.bar(x + i * width, values, width, bottom=bottom, color=colors[i], edgecolor='black')
        for j, td_count in enumerate(values):
            if td_count > 0:
                ax2.text(x[j] + i * width, bottom[j] + td_count / 2, f'{td_count} d.',
                         ha='center', va='center', fontsize=8, color='black', fontweight='bold')

    ax2.set_xticks(x + width * 2)
    ax2.set_xticklabels([a.upper() for a in assets_list], fontsize=11)
    ax2.set_ylabel('Number of trading days')
    ax2.set_title('Distribution over 175 trading days', fontsize=12, fontweight='bold')
    ax2.set_ylim(0, 175)
    ax2.grid(axis='y', alpha=0.3)
    legend_elements = [
        plt.Line2D([0], [0], marker='s', color='w', markerfacecolor=colors[i],
                   markersize=10, label=level_names[i])
        for i in range(len(level_names))
    ]
    ax2.legend(handles=legend_elements, fontsize=8, loc='center left', bbox_to_anchor=(1.02, 0.5))
    plt.suptitle(
        'Sentiment: ' + ', '.join([a.upper() for a in assets_list]) +
        ' (CFTC, 175 Trading Days)\nby Megatrend',
        fontsize=14, fontweight='bold', y=0.995
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf


# ────────────────────────────────────────────────
# Ежедневная отправка в 03:00 UTC
# ────────────────────────────────────────────────
async def daily_sender():
    if not CHAT_ID:
        logger.warning("CHAT_ID не задан — ежедневная отправка отключена")
        return

    while True:
        now      = datetime.now(timezone.utc)
        next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if now >= next_run:
            next_run = next_run.replace(day=next_run.day + 1)
        wait_sec = (next_run - now).total_seconds()
        logger.info(f"Ежедневная отправка через {wait_sec:.0f} сек ({next_run.strftime('%Y-%m-%d %H:%M UTC')})")
        await asyncio.sleep(wait_sec)

        logger.info("Запуск ежедневной отправки графиков...")
        try:
            for cmd, ticker in FUTURES.items():
                df = smart_money_flow(ticker)
                if df is None:
                    continue
                buf = make_chart(df, cmd.upper())
                await bot_app.bot.send_photo(
                    chat_id=CHAT_ID,
                    photo=buf,
                    caption=f"{cmd.upper()} — Volume Stress / Participation Index + RSX(9)"
                )
            buf_dist = make_distribution_chart()
            if buf_dist:
                await bot_app.bot.send_photo(
                    chat_id=CHAT_ID,
                    photo=buf_dist,
                    caption="Distribution (175 Trading Days)"
                )
            logger.info("Ежедневная отправка завершена")
        except Exception as e:
            logger.error(f"Ошибка ежедневной отправки: {e}")


# ────────────────────────────────────────────────
# Команды
# ────────────────────────────────────────────────
async def handle_asset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        asset = update.message.text.replace('/', '').lower()
        if asset not in FUTURES:
            await update.message.reply_text("Unknown command.")
            return
        await update.message.reply_text(f"Fetching {asset.upper()} data...")
        df = smart_money_flow(FUTURES[asset])
        if df is None:
            await update.message.reply_text("Not enough data.")
            return
        rsx       = calculate_rsx(df['Flow'], length=9)
        last_flow = float(df['Flow'].iloc[-1]) if len(df)  > 0 else None
        last_rsx  = float(rsx.iloc[-1])        if len(rsx) > 0 else None
        buf = make_chart(df, asset.upper())
        await update.message.reply_photo(photo=buf)
        txt  = f"{asset.upper()}:\n"
        txt += f"Participation Index: {last_flow:.1f}%\n" if last_flow is not None else "Participation Index: n/a\n"
        txt += f"RSX(9): {last_rsx:.1f}\n"               if last_rsx  is not None else "RSX(9): n/a\n"
        txt += f"Date: {df.index[-1].strftime('%d.%m.%Y')}"
        await update.message.reply_text(txt)
    except Exception as e:
        logger.error(f"Error in handle_asset: {e}")
        await update.message.reply_text(f"Error: {str(e)}")


async def distribution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("Generating distribution chart...")
        buf = make_distribution_chart()
        if buf:
            await update.message.reply_photo(photo=buf, caption="Smart Money Flow Distribution (175 Trading Days)")
        else:
            await update.message.reply_text("Could not generate chart.")
    except Exception as e:
        logger.error(f"Error in distribution: {e}")
        await update.message.reply_text(f"Error: {str(e)}")


async def all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text("Generating all charts...")
        for cmd in FUTURES.keys():
            df = smart_money_flow(FUTURES[cmd])
            if df is None:
                continue
            buf = make_chart(df, cmd.upper())
            await update.message.reply_photo(photo=buf, caption=f"{cmd.upper()} — Volume Stress / Participation Index + RSX(9)")
        bufd = make_distribution_chart()
        if bufd:
            await update.message.reply_photo(photo=bufd, caption="Distribution")
    except Exception as e:
        logger.error(f"Error in all_command: {e}")
        await update.message.reply_text(f"Error: {str(e)}")


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        txt  = "Volume Stress / Participation Index by Megatrend — commands:\n"
        txt += "/gc /cl /pl /6e /6j /dx — charts\n"
        txt += "/dist — distribution\n"
        txt += "/all — all charts + distribution\n"
        await update.message.reply_text(txt)
    except Exception as e:
        logger.error(f"Error in start_cmd: {e}")
        await update.message.reply_text(f"Error: {str(e)}")


# Регистрация команд
for cmd in FUTURES.keys():
    bot_app.add_handler(CommandHandler(cmd, handle_asset))
bot_app.add_handler(CommandHandler("dist",  distribution))
bot_app.add_handler(CommandHandler("all",   all_command))
bot_app.add_handler(CommandHandler("start", start_cmd))


# ────────────────────────────────────────────────
# Webhook + lifespan
# ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot_app.initialize()
    try:
        await bot_app.bot.set_webhook(f"{URL}/webhook")
        logger.info(f"Webhook set: {URL}/webhook")
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    await bot_app.start()
    task = asyncio.create_task(daily_sender())
    yield
    task.cancel()
    await bot_app.stop()


app = FastAPI(lifespan=lifespan)


@app.post("/webhook")
async def webhook(request: Request):
    try:
        json_update = await request.json()
        logger.info(f"Incoming update: {json_update}")
        update = Update.de_json(json_update, bot_app.bot)
        if update:
            await bot_app.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/test-gc")
async def test_gc():
    df = smart_money_flow(FUTURES['gc'])
    if df is None:
        raise HTTPException(status_code=503, detail="Not enough data")
    buf = make_chart(df, 'GC')
    return StreamingResponse(buf, media_type="image/png")


@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"status": "SmartMoney Bot alive!"}

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"status": "OK"}

@app.api_route("/ping", methods=["GET", "HEAD"])
async def ping():
    return {"status": "OK"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
