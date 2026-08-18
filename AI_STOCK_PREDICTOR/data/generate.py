"""
Processes the NSE wide-format CSV into per-stock OHLCV CSVs.
Since the dataset only has closing prices, we derive realistic
O/H/L/V using daily volatility estimates from the close series.
"""
import numpy as np
import pandas as pd
import json
import os

KAGGLE_PATH = r'C:\Users\vipul\.cache\kagglehub\datasets\stacknishant\nse-stock-historical-price-data\versions\1\nse_all_stock_data (1).csv'
OUT_DIR     = os.path.dirname(os.path.abspath(__file__))

# Top NSE stocks to expose in the app (well-known, liquid names)
TOP_STOCKS = [
    'RELIANCE', 'TCS', 'HDFCBANK', 'ICICIBANK', 'INFY',
    'SBIN', 'BHARTIARTL', 'ITC', 'HINDUNILVR', 'LT',
    'BAJFINANCE', 'HCLTECH', 'MARUTI', 'SUNPHARMA', 'KOTAKBANK',
    'TITAN', 'AXISBANK', 'WIPRO', 'TATAMOTORS', 'NTPC',
]

COMPANY_NAMES = {
    'RELIANCE':   'Reliance Industries',
    'TCS':        'Tata Consultancy Services',
    'HDFCBANK':   'HDFC Bank',
    'ICICIBANK':  'ICICI Bank',
    'INFY':       'Infosys',
    'SBIN':       'State Bank of India',
    'BHARTIARTL': 'Bharti Airtel',
    'ITC':        'ITC Limited',
    'HINDUNILVR': 'Hindustan Unilever',
    'LT':         'Larsen & Toubro',
    'BAJFINANCE': 'Bajaj Finance',
    'HCLTECH':    'HCL Technologies',
    'MARUTI':     'Maruti Suzuki',
    'SUNPHARMA':  'Sun Pharmaceutical',
    'KOTAKBANK':  'Kotak Mahindra Bank',
    'TITAN':      'Titan Company',
    'AXISBANK':   'Axis Bank',
    'WIPRO':      'Wipro',
    'TATAMOTORS': 'Tata Motors',
    'NTPC':       'NTPC Limited',
}

np.random.seed(42)

print('Loading dataset...')
df_raw = pd.read_csv(KAGGLE_PATH, encoding='latin1', low_memory=False)
df_raw['Date'] = pd.to_datetime(df_raw['Date'], errors='coerce')
df_raw = df_raw.dropna(subset=['Date']).sort_values('Date').reset_index(drop=True)

meta = {}

for symbol in TOP_STOCKS:
    if symbol not in df_raw.columns:
        print(f'  SKIP {symbol} - not in dataset')
        continue

    s = df_raw[['Date', symbol]].copy()
    s.columns = ['date', 'close']
    s['close'] = pd.to_numeric(s['close'], errors='coerce')
    s = s.dropna(subset=['close'])

    # keep only last 5 years for performance
    cutoff = s['date'].max() - pd.DateOffset(years=5)
    s = s[s['date'] >= cutoff].copy()

    if len(s) < 50:
        print(f'  SKIP {symbol} - insufficient data ({len(s)} rows)')
        continue

    s = s.reset_index(drop=True)
    close = s['close'].values
    n     = len(close)

    # derive daily volatility from rolling 20-day std of returns
    ret   = np.diff(np.log(close), prepend=np.log(close[0]))
    vol   = pd.Series(ret).rolling(20, min_periods=1).std().fillna(0.01).values

    daily_range = close * vol * 1.5
    high  = np.round(close + daily_range * np.random.uniform(0.3, 0.7, n), 2)
    low   = np.round(close - daily_range * np.random.uniform(0.3, 0.7, n), 2)
    open_ = np.round(low + (high - low) * np.random.uniform(0.1, 0.9, n), 2)

    base_vol = 10_000_000
    volume   = (base_vol * np.random.lognormal(0, 0.5, n)).astype(int)

    out = pd.DataFrame({
        'date':   s['date'].dt.strftime('%Y-%m-%d'),
        'open':   open_,
        'high':   high,
        'low':    low,
        'close':  np.round(close, 2),
        'volume': volume,
    })

    csv_path = os.path.join(OUT_DIR, f'{symbol}.csv')
    out.to_csv(csv_path, index=False)

    meta[symbol] = {
        'symbol':     symbol,
        'name':       COMPANY_NAMES.get(symbol, symbol),
        'current':    float(out['close'].iloc[-1]),
        'open':       float(out['open'].iloc[-1]),
        'high':       float(out['high'].iloc[-1]),
        'low':        float(out['low'].iloc[-1]),
        'volume':     int(out['volume'].iloc[-1]),
        'change':     round(float(out['close'].iloc[-1] - out['close'].iloc[-2]), 2),
        'change_pct': round(float((out['close'].iloc[-1] - out['close'].iloc[-2]) / out['close'].iloc[-2] * 100), 2),
        'rows':       len(out),
    }
    print(f'  {symbol}: {len(out)} rows, last close={out["close"].iloc[-1]}')

with open(os.path.join(OUT_DIR, 'stocks_meta.json'), 'w') as f:
    json.dump(meta, f, indent=2)

print(f'\nDone. {len(meta)} stocks processed.')
