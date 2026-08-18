import numpy as np
import pandas as pd
import json
import os
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import MinMaxScaler

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
PREDICT_DAYS = 30

STOCKS = [
    'RELIANCE', 'TCS', 'HDFCBANK', 'ICICIBANK', 'INFY',
    'SBIN', 'BHARTIARTL', 'ITC', 'HINDUNILVR', 'LT',
    'BAJFINANCE', 'HCLTECH', 'MARUTI', 'SUNPHARMA', 'KOTAKBANK',
    'TITAN', 'AXISBANK', 'WIPRO', 'TATAMOTORS', 'NTPC',
]

def make_features(df):
    df = df.copy()
    df['ma5']   = df['close'].rolling(5).mean()
    df['ma20']  = df['close'].rolling(20).mean()
    df['ma50']  = df['close'].rolling(50).mean()
    df['std20'] = df['close'].rolling(20).std()
    df['rsi']   = compute_rsi(df['close'], 14)
    df['ret1']  = df['close'].pct_change(1)
    df['ret5']  = df['close'].pct_change(5)
    df['vol_ma5'] = df['volume'].rolling(5).mean()
    df = df.dropna()
    return df

def compute_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

predictions = {}

for symbol in STOCKS:
    csv_path = os.path.join(DATA_DIR, f'{symbol}.csv')
    df = pd.read_csv(csv_path)
    df = make_features(df)

    feature_cols = ['ma5', 'ma20', 'ma50', 'std20', 'rsi', 'ret1', 'ret5', 'vol_ma5']
    X = df[feature_cols].values
    y = df['close'].values

    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X)

    model = LinearRegression()
    model.fit(X_scaled, y)

    # predict next PREDICT_DAYS days by rolling forward last known features
    last_row = df.iloc[-1].copy()
    future_closes = []
    future_opens  = []
    future_highs  = []
    future_lows   = []

    sim_close = last_row['close']
    sim_ma5   = last_row['ma5']
    sim_ma20  = last_row['ma20']
    sim_ma50  = last_row['ma50']
    sim_std20 = last_row['std20']
    sim_rsi   = last_row['rsi']
    sim_ret1  = last_row['ret1']
    sim_ret5  = last_row['ret5']
    sim_vol_ma5 = last_row['vol_ma5']

    for _ in range(PREDICT_DAYS):
        feat = np.array([[sim_ma5, sim_ma20, sim_ma50, sim_std20,
                          sim_rsi, sim_ret1, sim_ret5, sim_vol_ma5]])
        feat_scaled = scaler.transform(feat)
        pred_close = float(model.predict(feat_scaled)[0])

        daily_range = sim_std20 * 1.5
        pred_open  = round(sim_close + (pred_close - sim_close) * np.random.uniform(0.1, 0.5), 2)
        pred_high  = round(pred_close + abs(np.random.normal(0, daily_range * 0.5)), 2)
        pred_low   = round(pred_close - abs(np.random.normal(0, daily_range * 0.5)), 2)
        pred_close = round(pred_close, 2)

        future_closes.append(pred_close)
        future_opens.append(pred_open)
        future_highs.append(pred_high)
        future_lows.append(pred_low)

        # roll features forward
        sim_ret1  = (pred_close - sim_close) / sim_close
        sim_ret5  = sim_ret1  # simplified
        sim_ma5   = round((sim_ma5 * 4 + pred_close) / 5, 4)
        sim_ma20  = round((sim_ma20 * 19 + pred_close) / 20, 4)
        sim_ma50  = round((sim_ma50 * 49 + pred_close) / 50, 4)
        sim_close = pred_close

    # build future dates (business days)
    last_date = pd.to_datetime(df['date'].iloc[-1])
    future_dates = pd.bdate_range(start=last_date + pd.offsets.BDay(1), periods=PREDICT_DAYS)

    predictions[symbol] = {
        'dates':  [d.strftime('%Y-%m-%d') for d in future_dates],
        'open':   future_opens,
        'high':   future_highs,
        'low':    future_lows,
        'close':  future_closes,
        'target': future_closes[-1],
        'direction': 'up' if future_closes[-1] > df['close'].iloc[-1] else 'down',
        'confidence': round(min(99, max(51, abs(model.score(X_scaled, y)) * 100)), 1),
    }
    print(f'{symbol}: target={future_closes[-1]}, dir={predictions[symbol]["direction"]}, score={predictions[symbol]["confidence"]}%')

out_path = os.path.join(DATA_DIR, 'predictions.json')
with open(out_path, 'w') as f:
    json.dump(predictions, f, indent=2)

print(f'\nPredictions saved to {out_path}')
