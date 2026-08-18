from flask import Flask, render_template, jsonify, request
import os
import json
import time
import requests
import pandas as pd

app = Flask(__name__)

# ── Alpha Vantage ─────────────────────────────────────────────────────────────
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
AV_CACHE = {}   # { symbol: { data: {}, ts: float } }
AV_TTL   = 300  # 5 min cache — free tier is 25 req/day

def load_env():
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    return env

def save_env(data):
    existing = load_env()
    existing.update(data)
    with open(ENV_FILE, 'w') as f:
        for k, v in existing.items():
            f.write(f'{k}={v}\n')

def get_av_key():
    return load_env().get('AV_API_KEY') or os.environ.get('AV_API_KEY', '')

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
STOCKS = [
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

def load_csv(symbol):
    path = os.path.join(DATA_DIR, f'{symbol}.csv')
    return pd.read_csv(path)

def load_predictions():
    path = os.path.join(DATA_DIR, 'predictions.json')
    with open(path) as f:
        return json.load(f)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/settings')
def settings():
    return render_template('settings.html')

@app.route('/algo')
def algo():
    return render_template('algo.html')

@app.route('/api/stocks')
def stocks():
    preds = load_predictions()
    result = []
    for symbol in STOCKS:
        df = load_csv(symbol)
        last  = df.iloc[-1]
        prev  = df.iloc[-2]
        change     = round(float(last['close'] - prev['close']), 2)
        change_pct = round(float((last['close'] - prev['close']) / prev['close'] * 100), 2)
        result.append({
            'symbol':     symbol,
            'name':       COMPANY_NAMES[symbol],
            'price':      round(float(last['close']), 2),
            'open':       round(float(last['open']), 2),
            'high':       round(float(last['high']), 2),
            'low':        round(float(last['low']), 2),
            'volume':     int(last['volume']),
            'change':     change,
            'change_pct': change_pct,
            'direction':  preds[symbol]['direction'],
            'target':     preds[symbol]['target'],
            'confidence': preds[symbol]['confidence'],
        })
    return jsonify(result)

@app.route('/api/chart/<symbol>')
def chart(symbol):
    if symbol not in STOCKS:
        return jsonify({'error': 'Unknown symbol'}), 404

    period = request.args.get('period', '1Y')
    df = load_csv(symbol)

    period_map = {'1M': 21, '3M': 63, '6M': 126, '1Y': 252, '2Y': 504, 'ALL': len(df)}
    rows = period_map.get(period, 252)
    df = df.tail(rows)

    # compute indicators
    df = df.copy()
    df['ma20'] = df['close'].rolling(20).mean().round(2)
    df['ma50'] = df['close'].rolling(50).mean().round(2)

    candles = df[['date', 'open', 'high', 'low', 'close', 'volume']].to_dict(orient='records')
    ma20    = df[['date', 'ma20']].dropna().rename(columns={'ma20': 'value'}).to_dict(orient='records')
    ma50    = df[['date', 'ma50']].dropna().rename(columns={'ma50': 'value'}).to_dict(orient='records')

    preds = load_predictions()[symbol]

    return jsonify({
        'symbol':      symbol,
        'name':        COMPANY_NAMES[symbol],
        'candles':     candles,
        'ma20':        ma20,
        'ma50':        ma50,
        'predictions': preds,
    })

@app.route('/api/predict/<symbol>')
def predict(symbol):
    if symbol not in STOCKS:
        return jsonify({'error': 'Unknown symbol'}), 404
    preds = load_predictions()
    return jsonify(preds[symbol])

# ── Settings ─────────────────────────────────────────────────────────────────
@app.route('/api/settings', methods=['GET'])
def get_settings():
    env = load_env()
    return jsonify({
        'AV_API_KEY': env.get('AV_API_KEY', ''),
    })

@app.route('/api/settings', methods=['POST'])
def save_settings():
    body = request.get_json()
    if not body or 'AV_API_KEY' not in body:
        return jsonify({'status': 'error', 'message': 'AV_API_KEY required'}), 400
    key = body['AV_API_KEY'].strip()
    if not key:
        return jsonify({'status': 'error', 'message': 'Key cannot be empty'}), 400
    save_env({'AV_API_KEY': key})
    os.environ['AV_API_KEY'] = key
    AV_CACHE.clear()  # bust cache so next request uses new key
    return jsonify({'status': 'success'})

# ── Real-time quote via Alpha Vantage ─────────────────────────────────────────
@app.route('/api/realtime/<symbol>')
def realtime(symbol):
    if symbol not in STOCKS:
        return jsonify({'error': 'Unknown symbol'}), 404

    key = get_av_key()
    if not key:
        return jsonify({'error': 'Alpha Vantage API key not configured'}), 503

    # serve from cache if fresh
    cached = AV_CACHE.get(symbol)
    if cached and (time.time() - cached['ts']) < AV_TTL:
        return jsonify(cached['data'])

    # NSE stocks on Alpha Vantage use SYMBOL.BSE suffix
    av_symbol = f'{symbol}.BSE'
    url = 'https://www.alphavantage.co/query'
    params = {
        'function': 'GLOBAL_QUOTE',
        'symbol':   av_symbol,
        'apikey':   key,
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        raw = r.json()
    except Exception as e:
        return jsonify({'error': f'Alpha Vantage request failed: {e}'}), 502

    if 'Note' in raw:
        return jsonify({'error': 'Alpha Vantage rate limit hit. Try again in a minute.'}), 429

    if 'Information' in raw:
        return jsonify({'error': raw['Information']}), 429

    quote = raw.get('Global Quote', {})
    if not quote or not quote.get('05. price'):
        return jsonify({'error': f'No data returned for {av_symbol}'}), 404

    data = {
        'symbol':      symbol,
        'av_symbol':   av_symbol,
        'price':       float(quote.get('05. price', 0)),
        'open':        float(quote.get('02. open', 0)),
        'high':        float(quote.get('03. high', 0)),
        'low':         float(quote.get('04. low', 0)),
        'prev_close':  float(quote.get('08. previous close', 0)),
        'change':      float(quote.get('09. change', 0)),
        'change_pct':  quote.get('10. change percent', '0%').replace('%', '').strip(),
        'volume':      int(quote.get('06. volume', 0)),
        'latest_day':  quote.get('07. latest trading day', ''),
        'cached_at':   time.strftime('%H:%M:%S'),
    }

    AV_CACHE[symbol] = {'data': data, 'ts': time.time()}
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
