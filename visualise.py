import psycopg2
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host='localhost',
    database='stocks_db',
    user='postgres',
    password=os.environ.get('DB_PASSWORD'),
    port='5432'
)

# ── 1. PRICE CHART WITH MOVING AVERAGES ────────────────────────────────────
def plot_price(ticker):
    prices = pd.read_sql(f"""
        SELECT date, close_price
        FROM stock_prices
        WHERE ticker = '{ticker}'
        ORDER BY date
    """, conn)

    mas = pd.read_sql(f"""
        SELECT date, ma_7, ma_30, ma_90
        FROM moving_averages
        WHERE ticker = '{ticker}'
        ORDER BY date
    """, conn)

    prices['date'] = pd.to_datetime(prices['date'])
    mas['date'] = pd.to_datetime(mas['date'])

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(prices['date'], prices['close_price'], color='#5b4fcf', linewidth=1.5, label='Price')
    ax.plot(mas['date'], mas['ma_7'],  color='#f59e0b', linewidth=1, linestyle='--', label='7-day MA')
    ax.plot(mas['date'], mas['ma_30'], color='#22c55e', linewidth=1, linestyle='--', label='30-day MA')
    ax.plot(mas['date'], mas['ma_90'], color='#ef4444', linewidth=1, linestyle='--', label='90-day MA')

    ax.set_title(f'{ticker} — Price & Moving Averages', fontsize=16, fontweight='bold')
    ax.set_ylabel('Price ($)')
    ax.set_xlabel('Date')
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f'{ticker}_price.png', dpi=150)
    plt.show()
    print(f'Saved {ticker}_price.png')

# ── 2. ALL STOCKS COMPARISON ───────────────────────────────────────────────
def plot_all_stocks():
    df = pd.read_sql("""
        SELECT ticker, date, close_price
        FROM stock_prices
        ORDER BY ticker, date
    """, conn)

    df['date'] = pd.to_datetime(df['date'])

    # Normalise to 100 at start so we can compare performance
    fig, ax = plt.subplots(figsize=(14, 7))

    colors = ['#5b4fcf', '#22c55e', '#ef4444', '#f59e0b', '#06b6d4', '#ec4899', '#8b5cf6']

    for i, (ticker, group) in enumerate(df.groupby('ticker')):
        group = group.sort_values('date')
        normalised = (group['close_price'] / group['close_price'].iloc[0]) * 100
        ax.plot(group['date'], normalised, label=ticker,
                color=colors[i % len(colors)], linewidth=1.5)

    ax.axhline(y=100, color='gray', linestyle='--', linewidth=0.8, alpha=0.5)
    ax.set_title('Stock Performance (Normalised to 100)', fontsize=16, fontweight='bold')
    ax.set_ylabel('Performance (100 = start)')
    ax.set_xlabel('Date')
    ax.legend(loc='upper left')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('all_stocks.png', dpi=150)
    plt.show()
    print('Saved all_stocks.png')

# ── 3. TODAY'S PERFORMANCE BAR CHART ──────────────────────────────────────
def plot_today():
    df = pd.read_sql("""
        SELECT ticker, close_price,
               ROUND(
                   (close_price - LAG(close_price) OVER (PARTITION BY ticker ORDER BY date))
                   / LAG(close_price) OVER (PARTITION BY ticker ORDER BY date) * 100
               , 2) as pct_change
        FROM stock_prices
        WHERE date >= CURRENT_DATE - INTERVAL '2 days'
        ORDER BY ticker, date DESC
    """, conn)

    latest = df.groupby('ticker').first().reset_index()
    latest = latest.dropna(subset=['pct_change'])
    latest = latest.sort_values('pct_change', ascending=True)

    colors = ['#22c55e' if x > 0 else '#ef4444' for x in latest['pct_change']]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(latest['ticker'], latest['pct_change'], color=colors)
    ax.axvline(x=0, color='black', linewidth=0.8)
    ax.set_xlabel('% Change')
    ax.set_title("Today's Stock Performance", fontsize=16, fontweight='bold')
    ax.bar_label(bars, fmt='%.2f%%', padding=3)
    plt.tight_layout()
    plt.savefig('today_performance.png', dpi=150)
    plt.show()
    print('Saved today_performance.png')

# ── 4. VOLUME CHART ────────────────────────────────────────────────────────
def plot_volume(ticker):
    df = pd.read_sql(f"""
        SELECT date, volume, close_price
        FROM stock_prices
        WHERE ticker = '{ticker}'
        ORDER BY date
    """, conn)

    df['date'] = pd.to_datetime(df['date'])

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    # Price on top
    ax1.plot(df['date'], df['close_price'], color='#5b4fcf', linewidth=1.5)
    ax1.set_ylabel('Price ($)')
    ax1.set_title(f'{ticker} — Price and Volume', fontsize=16, fontweight='bold')

    # Volume on bottom
    ax2.bar(df['date'], df['volume'], color='#a78bfa', alpha=0.7)
    ax2.set_ylabel('Volume')
    ax2.set_xlabel('Date')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f'{ticker}_volume.png', dpi=150)
    plt.show()
    print(f'Saved {ticker}_volume.png')

# ── 5. ALERTS HISTORY ──────────────────────────────────────────────────────
def plot_alerts():
    df = pd.read_sql("""
        SELECT ticker, alert_type, change_pct, alert_date
        FROM price_alerts
        ORDER BY created_at DESC
        LIMIT 20
    """, conn)

    if len(df) == 0:
        print('No alerts yet — no stocks moved 3%+ today!')
        return

    colors = {
        'SPIKE UP':     '#22c55e',
        'SPIKE DOWN':   '#ef4444',
        'NOTABLE UP':   '#86efac',
        'NOTABLE DOWN': '#fca5a5',
    }

    fig, ax = plt.subplots(figsize=(12, 6))
    bar_colors = [colors.get(t, '#gray') for t in df['alert_type']]
    labels = [f"{row['ticker']} ({row['alert_date']})" for _, row in df.iterrows()]
    ax.barh(labels[::-1], df['change_pct'][::-1], color=bar_colors[::-1])
    ax.axvline(x=0, color='black', linewidth=0.8)
    ax.set_xlabel('% Change')
    ax.set_title('Price Alerts History', fontsize=16, fontweight='bold')
    plt.tight_layout()
    plt.savefig('alerts.png', dpi=150)
    plt.show()
    print('Saved alerts.png')

# ── RUN ALL ────────────────────────────────────────────────────────────────
print('Generating visualisations...')
plot_all_stocks()
plot_today()
plot_volume('AAPL')
plot_price('AAPL')
plot_price('NVDA')
plot_alerts()

conn.close()
print('\nAll charts saved!')