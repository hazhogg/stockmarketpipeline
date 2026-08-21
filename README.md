# Stock Market Data Pipeline

An automated data engineering pipeline that tracks live stock prices for 7 major tech companies, calculates moving averages, detects price spikes and stores everything in PostgreSQL.

## What it does

- Fetches live stock prices from Yahoo Finance (free, no API key needed)
- Tracks 7 major tech stocks daily
- Calculates 7, 30 and 90 day moving averages
- Alerts when a stock moves 5%+ in a day
- Stores all data in PostgreSQL for historical analysis
- Generates 5 visualisation charts
- Runs automatically at market open and close

## Stocks tracked

| Ticker | Company |
|---|---|
| AAPL | Apple |
| GOOGL | Google |
| MSFT | Microsoft |
| AMZN | Amazon |
| TSLA | Tesla |
| NVDA | Nvidia |
| META | Meta |

## Tech stack

- Python
- pandas
- PostgreSQL
- psycopg2
- yfinance (Yahoo Finance)
- schedule
- matplotlib
- Docker

## Database tables

### stock_prices
Daily OHLCV data for each stock:

| Column | Description |
|---|---|
| ticker | Stock symbol (AAPL, GOOGL etc.) |
| company | Company name |
| date | Trading date |
| open_price | Opening price |
| high_price | Daily high |
| low_price | Daily low |
| close_price | Closing price |
| volume | Shares traded |

### moving_averages
Rolling averages calculated from price history:

| Column | Description |
|---|---|
| ticker | Stock symbol |
| date | Date |
| ma_7 | 7-day moving average |
| ma_30 | 30-day moving average |
| ma_90 | 90-day moving average |

### price_alerts
Significant price movements flagged automatically:

| Column | Description |
|---|---|
| ticker | Stock symbol |
| alert_type | SPIKE UP / SPIKE DOWN / NOTABLE UP / NOTABLE DOWN |
| change_pct | Percentage change |
| close_price | Price at time of alert |
| message | Human readable alert message |

## Alert thresholds

```
5%+ move  → SPIKE UP / SPIKE DOWN
3%+ move  → NOTABLE UP / NOTABLE DOWN
```

## Setup

### Option 1 — Docker (recommended)

1. Clone the repo:
```bash
git clone https://github.com/yourusername/stock-market-pipeline.git
cd stock-market-pipeline
```

2. Create a `.env` file:
```
DB_PASSWORD=yourpassword
DB_HOST=db
```

3. Run:
```bash
docker compose up --build
```

### Option 2 — Local

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file:
```
DB_PASSWORD=yourpassword
DB_HOST=localhost
```

3. Run:
```bash
python stock_pipeline.py
```

## Visualisations

```bash
python visualise.py
```

Generates 5 charts:
- Stock performance normalised to 100 (compare all stocks)
- Today's % change per stock
- Price and volume chart per stock
- Price with 7, 30 and 90 day moving averages
- Price alerts history

## Example queries

```sql
-- Latest prices for all stocks
SELECT ticker, close_price, date
FROM stock_prices
WHERE date = (SELECT MAX(date) FROM stock_prices)
ORDER BY close_price DESC;

-- Best performing stock over last 30 days
SELECT ticker,
       ROUND((MAX(close_price) - MIN(close_price)) / MIN(close_price) * 100, 2) as pct_change
FROM stock_prices
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY ticker
ORDER BY pct_change DESC;

-- All alerts triggered
SELECT ticker, alert_type, change_pct, message, created_at
FROM price_alerts
ORDER BY created_at DESC;

-- Moving average crossover (price above 30-day MA = bullish)
SELECT s.ticker, s.close_price, m.ma_30,
       CASE WHEN s.close_price > m.ma_30 THEN 'Bullish' ELSE 'Bearish' END as signal
FROM stock_prices s
JOIN moving_averages m ON s.ticker = m.ticker AND s.date = m.date
WHERE s.date = (SELECT MAX(date) FROM stock_prices)
ORDER BY s.ticker;
```

## Schedule

Pipeline runs automatically:
```
14:30 UTC  → NYSE market open (9:30am EST)
21:00 UTC  → NYSE market close (4:00pm EST)
21:30 UTC  → post close update
```

## Project structure

```
stock-market-pipeline/
├── stock_pipeline.py  ← main ETL pipeline
├── visualise.py       ← chart generation
├── requirements.txt   ← dependencies
├── Dockerfile         ← Docker configuration
├── docker-compose.yml ← multi-container setup
├── .gitignore         ← excludes .env and charts
└── .env               ← credentials (not pushed)
```

## Author

Harry
