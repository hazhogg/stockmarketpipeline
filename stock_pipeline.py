import yfinance as yf
import psycopg2
import pandas as pd
import os
import schedule
import time
import warnings
from datetime import datetime
from dotenv import load_dotenv

warnings.filterwarnings('ignore')
load_dotenv()

# ── CONFIG ─────────────────────────────────────────────────────────────────
STOCKS = {
    'AAPL':  'Apple',
    'GOOGL': 'Google',
    'MSFT':  'Microsoft',
    'AMZN':  'Amazon',
    'TSLA':  'Tesla',
    'NVDA':  'Nvidia',
    'META':  'Meta',
}

DB_CONFIG = {
    'host':     os.environ.get('DB_HOST', 'localhost'),
    'database': 'stocks_db',
    'user':     'postgres',
    'password': os.environ.get('DB_PASSWORD'),
    'port':     '5432'
}

# ── SETUP DATABASE ─────────────────────────────────────────────────────────
def setup_database(conn):
    cursor = conn.cursor()

    # Daily prices table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stock_prices (
            id            SERIAL PRIMARY KEY,
            ticker        VARCHAR(10),
            company       VARCHAR(100),
            date          DATE,
            open_price    NUMERIC,
            high_price    NUMERIC,
            low_price     NUMERIC,
            close_price   NUMERIC,
            volume        BIGINT,
            fetched_at    TIMESTAMP,
            UNIQUE(ticker, date)
        )
    """)

    # Alerts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS price_alerts (
            id          SERIAL PRIMARY KEY,
            ticker      VARCHAR(10),
            company     VARCHAR(100),
            alert_date  DATE,
            alert_type  VARCHAR(50),
            change_pct  NUMERIC,
            close_price NUMERIC,
            message     TEXT,
            created_at  TIMESTAMP
        )
    """)

    # Moving averages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS moving_averages (
            id          SERIAL PRIMARY KEY,
            ticker      VARCHAR(10),
            date        DATE,
            ma_7        NUMERIC,
            ma_30       NUMERIC,
            ma_90       NUMERIC,
            fetched_at  TIMESTAMP,
            UNIQUE(ticker, date)
        )
    """)

    conn.commit()
    print('Database ready!')

# ── EXTRACT ────────────────────────────────────────────────────────────────
def extract(ticker):
    print(f'  Extracting {ticker}...')
    stock = yf.Ticker(ticker)

    # Get 6 months of history for moving averages
    hist = stock.history(period='6mo')

    if hist.empty:
        raise Exception(f'No data returned for {ticker}')

    return hist

# ── TRANSFORM ──────────────────────────────────────────────────────────────
def transform(hist, ticker, company):
    print(f'  Transforming {ticker}...')

    df = hist.copy()
    df = df.reset_index()

    # Clean column names
    df.columns = [c.lower().replace(' ', '_') for c in df.columns]

    # Keep only what we need
    df = df[['date', 'open', 'high', 'low', 'close', 'volume']]
    df.columns = ['date', 'open_price', 'high_price', 'low_price', 'close_price', 'volume']

    # Remove timezone from date
    df['date'] = pd.to_datetime(df['date']).dt.date

    # Add metadata
    df['ticker']     = ticker
    df['company']    = company
    df['fetched_at'] = datetime.now()

    # Calculate daily % change
    df['pct_change'] = df['close_price'].pct_change() * 100
    df['pct_change'] = df['pct_change'].round(2)

    return df

# ── CALCULATE MOVING AVERAGES ───────────────────────────────────────────────
def calculate_moving_averages(df, ticker):
    print(f'  Calculating moving averages for {ticker}...')

    ma_df = pd.DataFrame()
    ma_df['date']   = df['date']
    ma_df['ticker'] = ticker
    ma_df['ma_7']   = df['close_price'].rolling(window=7).mean().round(2)
    ma_df['ma_30']  = df['close_price'].rolling(window=30).mean().round(2)
    ma_df['ma_90']  = df['close_price'].rolling(window=90).mean().round(2)
    ma_df['fetched_at'] = datetime.now()

    return ma_df.dropna()

# ── CHECK ALERTS ───────────────────────────────────────────────────────────
def check_alerts(df, ticker, company, conn):
    """Flag significant price movements"""
    today = df.iloc[-1]
    pct_change = today['pct_change']

    if pd.isna(pct_change):
        return

    alert_type = None
    message = None

    if pct_change >= 5:
        alert_type = 'SPIKE UP'
        message = f'{company} ({ticker}) UP {pct_change:.1f}% today! Close: ${today["close_price"]:.2f}'
        print(f'  🚀 ALERT: {message}')
    elif pct_change <= -5:
        alert_type = 'SPIKE DOWN'
        message = f'{company} ({ticker}) DOWN {pct_change:.1f}% today! Close: ${today["close_price"]:.2f}'
        print(f'  📉 ALERT: {message}')
    elif pct_change >= 3:
        alert_type = 'NOTABLE UP'
        message = f'{company} ({ticker}) up {pct_change:.1f}% today'
        print(f'  📈 Notable: {message}')
    elif pct_change <= -3:
        alert_type = 'NOTABLE DOWN'
        message = f'{company} ({ticker}) down {pct_change:.1f}% today'
        print(f'  📉 Notable: {message}')

    if alert_type:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO price_alerts
            (ticker, company, alert_date, alert_type, change_pct, close_price, message, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (ticker, company, today['date'], alert_type,
              pct_change, today['close_price'], message, datetime.now()))
        conn.commit()

# ── LOAD ───────────────────────────────────────────────────────────────────
def load_prices(df, conn):
    print(f'  Loading {len(df)} price rows...')
    cursor = conn.cursor()
    for _, row in df.iterrows():
        cursor.execute("""
            INSERT INTO stock_prices
            (ticker, company, date, open_price, high_price, low_price,
             close_price, volume, fetched_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (ticker, date) DO UPDATE SET
                close_price = EXCLUDED.close_price,
                volume      = EXCLUDED.volume,
                fetched_at  = EXCLUDED.fetched_at
        """, (row['ticker'], row['company'], row['date'],
              row['open_price'], row['high_price'], row['low_price'],
              row['close_price'], int(row['volume']), row['fetched_at']))
    conn.commit()

def load_moving_averages(df, conn):
    print(f'  Loading {len(df)} moving average rows...')
    cursor = conn.cursor()
    for _, row in df.iterrows():
        ma_7  = None if pd.isna(row['ma_7'])  else float(row['ma_7'])
        ma_30 = None if pd.isna(row['ma_30']) else float(row['ma_30'])
        ma_90 = None if pd.isna(row['ma_90']) else float(row['ma_90'])
        cursor.execute("""
            INSERT INTO moving_averages (ticker, date, ma_7, ma_30, ma_90, fetched_at)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (ticker, date) DO UPDATE SET
                ma_7  = EXCLUDED.ma_7,
                ma_30 = EXCLUDED.ma_30,
                ma_90 = EXCLUDED.ma_90,
                fetched_at = EXCLUDED.fetched_at
        """, (row['ticker'], row['date'], ma_7, ma_30, ma_90, row['fetched_at']))
    conn.commit()

# ── MAIN PIPELINE ──────────────────────────────────────────────────────────
def run_pipeline():
    print(f'\n[{datetime.now().strftime("%H:%M:%S")}] Running stock pipeline...')
    try:
        conn = psycopg2.connect(**DB_CONFIG)

        for ticker, company in STOCKS.items():
            print(f'\nProcessing {company} ({ticker})...')
            try:
                # Extract
                hist = extract(ticker)

                # Transform
                df = transform(hist, ticker, company)

                # Load prices
                load_prices(df, conn)

                # Moving averages
                ma_df = calculate_moving_averages(df, ticker)
                load_moving_averages(ma_df, conn)

                # Check alerts
                check_alerts(df, ticker, company, conn)

            except Exception as e:
                print(f'  ❌ Error processing {ticker}: {e}')
                continue

        # Summary
        print('\n--- Today\'s Market Summary ---')
        summary = pd.read_sql("""
            SELECT ticker, company,
                   close_price,
                   ROUND(
                       (close_price - LAG(close_price) OVER (PARTITION BY ticker ORDER BY date))
                       / LAG(close_price) OVER (PARTITION BY ticker ORDER BY date) * 100
                   , 2) as pct_change
            FROM stock_prices
            WHERE date >= CURRENT_DATE - INTERVAL '2 days'
            ORDER BY ticker, date DESC
        """, conn)

        latest = summary.groupby('ticker').first().reset_index()
        latest = latest.sort_values('pct_change', ascending=False)

        for _, row in latest.iterrows():
            if pd.isna(row['pct_change']):
                print(f"  {row['ticker']:6} ${row['close_price']:8.2f}")
            else:
                arrow = '↑' if row['pct_change'] > 0 else '↓'
                print(f"  {row['ticker']:6} ${row['close_price']:8.2f}  {arrow} {abs(row['pct_change']):.2f}%")

        # Recent alerts
        alerts = pd.read_sql("""
            SELECT ticker, alert_type, change_pct, message
            FROM price_alerts
            ORDER BY created_at DESC
            LIMIT 5
        """, conn)

        if len(alerts) > 0:
            print('\n--- Recent Alerts ---')
            for _, alert in alerts.iterrows():
                print(f"  {alert['message']}")

        conn.close()
        print('\n✅ Pipeline complete!')

    except Exception as e:
        print(f'❌ Pipeline failed: {e}')

# ── RUN ────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    # Create database first
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    try:
        setup_conn = psycopg2.connect(
            host='localhost', database='postgres',
            user='postgres', password=os.environ.get('DB_PASSWORD'), port='5432'
        )
        setup_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        setup_conn.cursor().execute('CREATE DATABASE stocks_db')
        setup_conn.close()
        print('stocks_db created!')
    except Exception as e:
        print(f'Database note: {e}')

    conn = psycopg2.connect(**DB_CONFIG)
    setup_database(conn)
    conn.close()

    run_pipeline()

    # Run every day at market open and close (NYSE hours)
    schedule.every().day.at('14:30').do(run_pipeline)  # 9:30am EST = 2:30pm UK
    schedule.every().day.at('21:00').do(run_pipeline)  # 4:00pm EST = 9pm UK
    schedule.every().day.at('21:30').do(run_pipeline)  # after close

    print('\nScheduler running — updates at market open and close.')
    print('Press Ctrl+C to stop.\n')

    while True:
        schedule.run_pending()
        time.sleep(60)