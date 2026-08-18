from flask import Flask, render_template, jsonify, request
import os
import json
import time
import requests
import datetime
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

def get_fmp_key():
    return load_env().get('FMP_API_KEY') or os.environ.get('FMP_API_KEY', '')

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
        price      = round(float(last['close']), 2)
        open_p     = round(float(last['open']), 2)
        high_p     = round(float(last['high']), 2)
        low_p      = round(float(last['low']), 2)
        vol        = int(last['volume'])

        # merge cached real-time quote if available
        cached = AV_CACHE.get(symbol)
        if cached:
            live = cached['data']
            price      = live.get('price', price)
            open_p     = live.get('open', open_p)
            high_p     = live.get('high', high_p)
            low_p      = live.get('low', low_p)
            change     = live.get('change', change)
            change_pct = live.get('change_pct', change_pct)
            vol        = live.get('volume', vol)

        result.append({
            'symbol':     symbol,
            'name':       COMPANY_NAMES[symbol],
            'price':      price,
            'open':       open_p,
            'high':       high_p,
            'low':        low_p,
            'volume':     vol,
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
    yf_symbol = SYMBOL_YF_MAP.get(symbol, f'{symbol}.NS')
    range_map = {'1M': '1m', '3M': '3m', '6M': '6m', '1Y': '1y', '2Y': '2y', 'ALL': '5y'}
    yf_range = range_map.get(period, '1y')
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    candles = []
    # 1. Try to fetch real-time chart candles up to today from Yahoo Finance
    try:
        yf_url = f'https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?range={yf_range}&interval=1d'
        r = requests.get(yf_url, headers=headers, timeout=5)
        if r.status_code == 200:
            result = r.json().get('chart', {}).get('result', [{}])[0]
            timestamps = result.get('timestamp', [])
            quote = result.get('indicators', {}).get('quote', [{}])[0]
            for i in range(len(timestamps)):
                c = quote.get('close', [])[i] if i < len(quote.get('close', [])) else None
                o = quote.get('open', [])[i] if i < len(quote.get('open', [])) else None
                h = quote.get('high', [])[i] if i < len(quote.get('high', [])) else None
                l = quote.get('low', [])[i] if i < len(quote.get('low', [])) else None
                v = quote.get('volume', [])[i] if i < len(quote.get('volume', [])) else 0
                if c is not None and o is not None and h is not None and l is not None:
                    dt = time.strftime('%Y-%m-%d', time.localtime(timestamps[i]))
                    candles.append({
                        'date':   dt,
                        'open':   float(round(o, 2)),
                        'high':   float(round(h, 2)),
                        'low':    float(round(l, 2)),
                        'close':  float(round(c, 2)),
                        'volume': int(v or 0)
                    })
    except Exception:
        pass

    # 2. Fallback to local CSV dataset if real-time chart fetch failed
    if not candles:
        df = load_csv(symbol)
        period_map = {'1M': 21, '3M': 63, '6M': 126, '1Y': 252, '2Y': 504, 'ALL': len(df)}
        rows = period_map.get(period, 252)
        df = df.tail(rows)
        candles = df[['date', 'open', 'high', 'low', 'close', 'volume']].to_dict(orient='records')

    # Append cached real-time quote for today if available and newer
    cached = AV_CACHE.get(symbol)
    if cached:
        live = cached['data']
        latest_day = live.get('latest_day') or time.strftime('%Y-%m-%d')
        if candles:
            if candles[-1]['date'] != latest_day:
                candles.append({
                    'date':   latest_day,
                    'open':   live.get('open', live['price']),
                    'high':   live.get('high', live['price']),
                    'low':    live.get('low', live['price']),
                    'close':  live['price'],
                    'volume': live.get('volume', 0)
                })
            else:
                candles[-1]['close']  = live['price']
                candles[-1]['high']   = max(candles[-1]['high'], live.get('high', live['price']))
                candles[-1]['low']    = min(candles[-1]['low'], live.get('low', live['price']))
                candles[-1]['volume'] = live.get('volume', candles[-1]['volume'])

    # Compute Moving Averages across candles
    cdf = pd.DataFrame(candles)
    cdf['ma20'] = cdf['close'].rolling(20).mean().round(2)
    cdf['ma50'] = cdf['close'].rolling(50).mean().round(2)

    ma20 = cdf[['date', 'ma20']].dropna().rename(columns={'ma20': 'value'}).to_dict(orient='records')
    ma50 = cdf[['date', 'ma50']].dropna().rename(columns={'ma50': 'value'}).to_dict(orient='records')

    # Compute dynamic AI forecast predictions starting from today's latest candle
    preds = load_predictions()[symbol]
    last_candle = candles[-1]
    last_date_str = last_candle['date']
    last_close = last_candle['close']

    try:
        start_dt = datetime.datetime.strptime(last_date_str, '%Y-%m-%d')
    except Exception:
        start_dt = datetime.datetime.now()

    future_dates = []
    curr = start_dt
    count = 0
    while count < len(preds['close']):
        curr += datetime.timedelta(days=1)
        if curr.weekday() < 5:  # Monday to Friday
            future_dates.append(curr.strftime('%Y-%m-%d'))
            count += 1

    ratio = (last_close / preds['close'][0]) if (preds['close'] and preds['close'][0] > 0) else 1.0
    scaled_close = [float(round(c * ratio, 2)) for c in preds['close']]
    target = float(round(preds['target'] * ratio, 2))

    dynamic_preds = {
        'direction':  preds['direction'],
        'target':     target,
        'confidence': preds['confidence'],
        'dates':      future_dates,
        'close':      scaled_close,
        'open':       [float(round(o * ratio, 2)) for o in preds['open']],
        'high':       [float(round(h * ratio, 2)) for h in preds['high']],
        'low':        [float(round(l * ratio, 2)) for l in preds['low']],
    }

    return jsonify({
        'symbol':      symbol,
        'name':        COMPANY_NAMES[symbol],
        'candles':     candles,
        'ma20':        ma20,
        'ma50':        ma50,
        'predictions': dynamic_preds,
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
        'FMP_API_KEY': env.get('FMP_API_KEY', ''),
        'AV_API_KEY':  env.get('AV_API_KEY', ''),
    })

@app.route('/api/settings', methods=['POST'])
def save_settings():
    body = request.get_json() or {}
    updated = {}
    if 'FMP_API_KEY' in body:
        updated['FMP_API_KEY'] = body['FMP_API_KEY'].strip()
        os.environ['FMP_API_KEY'] = updated['FMP_API_KEY']
    if 'AV_API_KEY' in body:
        updated['AV_API_KEY'] = body['AV_API_KEY'].strip()
        os.environ['AV_API_KEY'] = updated['AV_API_KEY']

    if not updated:
        return jsonify({'status': 'error', 'message': 'API key required'}), 400

    save_env(updated)
    AV_CACHE.clear()  # bust cache so next request uses new key
    return jsonify({'status': 'success'})

# ── Real-time quote via FMP, Alpha Vantage & Yahoo Finance Fallback ───────────
SYMBOL_FMP_MAP = {'TATAMOTORS': 'TMCV.NS'}
SYMBOL_YF_MAP  = {'TATAMOTORS': 'TMCV.NS'}
SYMBOL_AV_MAP  = {'TATAMOTORS': 'TMCV.BSE'}

@app.route('/api/realtime/<symbol>')
def realtime(symbol):
    if symbol not in STOCKS:
        return jsonify({'error': 'Unknown symbol'}), 404

    # serve from cache if fresh
    cached = AV_CACHE.get(symbol)
    if cached and (time.time() - cached['ts']) < AV_TTL:
        return jsonify(cached['data'])

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    # 1. Try Financial Modeling Prep (FMP) API
    fmp_key = get_fmp_key()
    if fmp_key:
        fmp_symbol = SYMBOL_FMP_MAP.get(symbol, f'{symbol}.NS')
        fmp_url = f'https://financialmodelingprep.com/stable/quote?symbol={fmp_symbol}&apikey={fmp_key}'
        try:
            r = requests.get(fmp_url, headers=headers, timeout=5)
            if r.status_code == 200:
                raw = r.json()
                if isinstance(raw, list) and len(raw) > 0 and 'price' in raw[0]:
                    q = raw[0]
                    price = float(q.get('price', 0))
                    if price > 0:
                        prev = float(q.get('previousClose', price))
                        chg = float(q.get('change', price - prev))
                        chg_pct = float(q.get('changePercentage', 0))
                        data = {
                            'symbol':      symbol,
                            'av_symbol':   fmp_symbol,
                            'price':       float(round(price, 2)),
                            'open':        float(round(q.get('open', price), 2)),
                            'high':        float(round(q.get('dayHigh', price), 2)),
                            'low':         float(round(q.get('dayLow', price), 2)),
                            'prev_close':  float(round(prev, 2)),
                            'change':      float(round(chg, 2)),
                            'change_pct':  float(round(chg_pct, 2)),
                            'volume':      int(q.get('volume', 0)),
                            'latest_day':  time.strftime('%Y-%m-%d'),
                            'cached_at':   time.strftime('%H:%M:%S'),
                            'source':      'Financial Modeling Prep (FMP)',
                        }
                        AV_CACHE[symbol] = {'data': data, 'ts': time.time()}
                        return jsonify(data)
        except Exception:
            pass

    # 2. Try Alpha Vantage if key is configured
    key = get_av_key()
    if key:
        av_symbol = SYMBOL_AV_MAP.get(symbol, f'{symbol}.BSE')
        url = 'https://www.alphavantage.co/query'
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol':   av_symbol,
            'apikey':   key,
        }
        try:
            r = requests.get(url, params=params, timeout=5)
            if r.status_code == 200:
                raw = r.json()
                quote = raw.get('Global Quote', {})
                if quote and quote.get('05. price'):
                    chg_str = quote.get('10. change percent', '0%').replace('%', '').strip()
                    data = {
                        'symbol':      symbol,
                        'av_symbol':   av_symbol,
                        'price':       float(quote.get('05. price', 0)),
                        'open':        float(quote.get('02. open', 0)),
                        'high':        float(quote.get('03. high', 0)),
                        'low':         float(quote.get('04. low', 0)),
                        'prev_close':  float(quote.get('08. previous close', 0)),
                        'change':      float(quote.get('09. change', 0)),
                        'change_pct':  float(chg_str),
                        'volume':      int(quote.get('06. volume', 0)),
                        'latest_day':  quote.get('07. latest trading day', ''),
                        'cached_at':   time.strftime('%H:%M:%S'),
                        'source':      'Alpha Vantage',
                    }
                    AV_CACHE[symbol] = {'data': data, 'ts': time.time()}
                    return jsonify(data)
        except Exception:
            pass

    # 3. Try Yahoo Finance real-time query
    yf_symbol = SYMBOL_YF_MAP.get(symbol, f'{symbol}.NS')
    try:
        yf_url = f'https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}'
        r = requests.get(yf_url, headers=headers, timeout=5)
        if r.status_code == 200:
            result = r.json().get('chart', {}).get('result', [{}])[0]
            meta = result.get('meta', {})
            price = meta.get('regularMarketPrice')
            if price is not None:
                prev = meta.get('chartPreviousClose', price)
                chg = price - prev if prev else 0.0
                chg_pct = (chg / prev * 100.0) if prev else 0.0
                open_p = meta.get('regularMarketDayOpen', price)
                high_p = meta.get('regularMarketDayHigh', price)
                low_p = meta.get('regularMarketDayLow', price)
                vol = meta.get('regularMarketVolume', 0)
                data = {
                    'symbol':      symbol,
                    'av_symbol':   yf_symbol,
                    'price':       float(round(price, 2)),
                    'open':        float(round(open_p, 2)),
                    'high':        float(round(high_p, 2)),
                    'low':         float(round(low_p, 2)),
                    'prev_close':  float(round(prev, 2)),
                    'change':      float(round(chg, 2)),
                    'change_pct':  float(round(chg_pct, 2)),
                    'volume':      int(vol or 0),
                    'latest_day':  time.strftime('%Y-%m-%d'),
                    'cached_at':   time.strftime('%H:%M:%S'),
                    'source':      'Yahoo Finance',
                }
                AV_CACHE[symbol] = {'data': data, 'ts': time.time()}
                return jsonify(data)
    except Exception:
        pass

    # 4. Fallback to latest record from local CSV dataset
    try:
        df = load_csv(symbol)
        last = df.iloc[-1]
        prev = df.iloc[-2]
        chg = float(last['close'] - prev['close'])
        chg_pct = float(chg / prev['close'] * 100.0)
        data = {
            'symbol':      symbol,
            'av_symbol':   f'{symbol}.BSE',
            'price':       float(round(last['close'], 2)),
            'open':        float(round(last['open'], 2)),
            'high':        float(round(last['high'], 2)),
            'low':         float(round(last['low'], 2)),
            'prev_close':  float(round(prev['close'], 2)),
            'change':      float(round(chg, 2)),
            'change_pct':  float(round(chg_pct, 2)),
            'volume':      int(last['volume']),
            'latest_day':  str(last['date']),
            'cached_at':   time.strftime('%H:%M:%S'),
            'source':      'Local Dataset',
        }
        AV_CACHE[symbol] = {'data': data, 'ts': time.time()}
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': f'Failed to load realtime quote: {e}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)


