let chart, candleSeries, ma20Series, ma50Series, predSeries, volSeries;
let currentSymbol = 'RELIANCE';
let currentPeriod = '1Y';
let allStocks = [];
let liveRefreshTimer = null;

// ── Init chart ──────────────────────────────────────────────────────────────
function initChart() {
    const chartEl  = document.getElementById('chart-container');
    const volumeEl = document.getElementById('volume-container');

    chart = LightweightCharts.createChart(chartEl, {
        layout:     { background: { color: 'transparent' }, textColor: '#94a3b8' },
        grid:       { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
        crosshair:  { mode: LightweightCharts.CrosshairMode.Normal },
        rightPriceScale: { borderColor: 'rgba(255,255,255,0.07)' },
        timeScale:  { borderColor: 'rgba(255,255,255,0.07)', timeVisible: true },
        handleScroll: true,
        handleScale:  true,
    });

    candleSeries = chart.addCandlestickSeries({
        upColor:   '#10b981', downColor: '#ef4444',
        borderUpColor: '#10b981', borderDownColor: '#ef4444',
        wickUpColor:   '#10b981', wickDownColor:   '#ef4444',
    });

    ma20Series = chart.addLineSeries({ color: '#f59e0b', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false });
    ma50Series = chart.addLineSeries({ color: '#a78bfa', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false });
    predSeries = chart.addLineSeries({ color: '#38bdf8', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dashed, priceLineVisible: false, lastValueVisible: true, title: 'Forecast' });

    // volume chart
    const volChart = LightweightCharts.createChart(volumeEl, {
        layout:     { background: { color: 'transparent' }, textColor: '#64748b' },
        grid:       { vertLines: { color: 'transparent' }, horzLines: { color: 'transparent' } },
        rightPriceScale: { borderColor: 'rgba(255,255,255,0.07)', scaleMargins: { top: 0.1, bottom: 0 } },
        timeScale:  { visible: false },
        handleScroll: false,
        handleScale:  false,
    });
    volSeries = volChart.addHistogramSeries({ color: 'rgba(59,130,246,0.4)', priceFormat: { type: 'volume' } });

    // sync timescales
    chart.timeScale().subscribeVisibleLogicalRangeChange(range => {
        if (range) volChart.timeScale().setVisibleLogicalRange(range);
    });

    // crosshair OHLCV update
    chart.subscribeCrosshairMove(param => {
        if (!param.time || !param.seriesData) return;
        const d = param.seriesData.get(candleSeries);
        if (d) {
            document.getElementById('stat-open').textContent  = '$' + d.open.toFixed(2);
            document.getElementById('stat-high').textContent  = '$' + d.high.toFixed(2);
            document.getElementById('stat-low').textContent   = '$' + d.low.toFixed(2);
            document.getElementById('stat-close').textContent = '$' + d.close.toFixed(2);
        }
        const v = param.seriesData.get(volSeries);
        if (v) document.getElementById('stat-vol').textContent = fmtVol(v.value);
    });

    // resize
    const ro = new ResizeObserver(() => {
        chart.applyOptions({ width: chartEl.clientWidth, height: chartEl.clientHeight });
        volChart.applyOptions({ width: volumeEl.clientWidth, height: volumeEl.clientHeight });
    });
    ro.observe(chartEl);
    ro.observe(volumeEl);
}

// ── Load chart data ──────────────────────────────────────────────────────────
async function loadChart(symbol, period) {
    const res  = await fetch(`/api/chart/${symbol}?period=${period}`);
    const data = await res.json();

    // candles
    const candles = data.candles.map(d => ({ time: d.date, open: d.open, high: d.high, low: d.low, close: d.close }));
    candleSeries.setData(candles);

    // volume
    const vols = data.candles.map(d => ({ time: d.date, value: d.volume, color: d.close >= d.open ? 'rgba(16,185,129,0.4)' : 'rgba(239,68,68,0.4)' }));
    volSeries.setData(vols);

    // MAs
    ma20Series.setData(data.ma20.map(d => ({ time: d.date, value: d.value })));
    ma50Series.setData(data.ma50.map(d => ({ time: d.date, value: d.value })));

    // forecast overlay — connect last candle to predictions
    const lastCandle = candles[candles.length - 1];
    const predData   = [{ time: lastCandle.time, value: lastCandle.close }];
    data.predictions.dates.forEach((dt, i) => predData.push({ time: dt, value: data.predictions.close[i] }));
    predSeries.setData(predData);

    // header stats (last bar)
    const last = data.candles[data.candles.length - 1];
    document.getElementById('chart-symbol').textContent = symbol;
    document.getElementById('chart-name').textContent   = data.name;
    document.getElementById('stat-open').textContent    = '$' + last.open.toFixed(2);
    document.getElementById('stat-high').textContent    = '$' + last.high.toFixed(2);
    document.getElementById('stat-low').textContent     = '$' + last.low.toFixed(2);
    document.getElementById('stat-close').textContent   = '$' + last.close.toFixed(2);
    document.getElementById('stat-vol').textContent     = fmtVol(last.volume);

    chart.timeScale().fitContent();
    updatePredPanel(data.predictions, last.close);
    fetchLiveQuote(symbol);
}

// ── Live quote (Alpha Vantage) ───────────────────────────────────────────────
async function fetchLiveQuote(symbol) {
    if (liveRefreshTimer) clearInterval(liveRefreshTimer);

    const doFetch = async () => {
        try {
            const res  = await fetch(`/api/realtime/${symbol}`);
            const data = await res.json();

            if (data.error) {
                document.getElementById('live-badge').style.display = 'none';
                document.getElementById('live-price-wrap').style.display = 'none';
                return;
            }

            const pct  = parseFloat(data.change_pct);
            const isUp = pct >= 0;
            const sign = isUp ? '+' : '';

            document.getElementById('live-badge').style.display      = 'inline-flex';
            document.getElementById('live-price-wrap').style.display = 'inline';
            document.getElementById('live-price').textContent        = '\u20b9' + data.price.toFixed(2);

            const chgEl = document.getElementById('live-change');
            chgEl.textContent = `${sign}${pct.toFixed(2)}%`;
            chgEl.style.color = isUp ? '#10b981' : '#ef4444';

            // overwrite OHLCV bar with live values
            document.getElementById('stat-open').textContent  = '\u20b9' + data.open.toFixed(2);
            document.getElementById('stat-high').textContent  = '\u20b9' + data.high.toFixed(2);
            document.getElementById('stat-low').textContent   = '\u20b9' + data.low.toFixed(2);
            document.getElementById('stat-close').textContent = '\u20b9' + data.price.toFixed(2);
            document.getElementById('stat-vol').textContent   = fmtVol(data.volume);
        } catch (_) { /* fail silently */ }
    };

    doFetch();
    liveRefreshTimer = setInterval(doFetch, 60000);
}

// ── Prediction panel ─────────────────────────────────────────────────────────
function updatePredPanel(pred, currentClose) {
    const target    = pred.target;
    const change    = target - currentClose;
    const changePct = (change / currentClose * 100).toFixed(2);
    const isUp      = pred.direction === 'up';

    const badge = document.getElementById('pred-badge');
    badge.textContent = isUp ? '▲ BULLISH' : '▼ BEARISH';
    badge.className   = 'pred-direction-badge ' + (isUp ? 'up' : 'down');

    document.getElementById('pred-target').textContent = '$' + target.toFixed(2);
    const chgEl = document.getElementById('pred-change');
    chgEl.textContent = (change >= 0 ? '+' : '') + change.toFixed(2) + ' (' + (change >= 0 ? '+' : '') + changePct + '%)';
    chgEl.className   = 'pred-change ' + (isUp ? 'positive' : 'negative');

    document.getElementById('conf-pct').textContent = pred.confidence + '%';
    document.getElementById('conf-bar').style.width = pred.confidence + '%';

    const lastIdx = pred.close.length - 1;
    document.getElementById('pred-open').textContent  = '$' + pred.open[lastIdx].toFixed(2);
    document.getElementById('pred-high').textContent  = '$' + pred.high[lastIdx].toFixed(2);
    document.getElementById('pred-low').textContent   = '$' + pred.low[lastIdx].toFixed(2);
    document.getElementById('pred-close').textContent = '$' + pred.close[lastIdx].toFixed(2);

    // insights
    const insights = [
        `30-day price target: <b>$${target.toFixed(2)}</b>`,
        `Expected move: <b>${(change >= 0 ? '+' : '') + changePct}%</b> from current price`,
        `Model confidence: <b>${pred.confidence}%</b>`,
        `Trend direction: <b>${isUp ? 'Upward momentum' : 'Downward pressure'}</b>`,
        `Forecast high: <b>$${Math.max(...pred.high).toFixed(2)}</b>`,
        `Forecast low: <b>$${Math.min(...pred.low).toFixed(2)}</b>`,
    ];
    document.getElementById('insights-list').innerHTML = insights.map(i => `<li>${i}</li>`).join('');
}

// ── Stock list ───────────────────────────────────────────────────────────────
async function loadStockList() {
    const res  = await fetch('/api/stocks');
    allStocks  = await res.json();
    renderStockList(allStocks);
}

function renderStockList(stocks) {
    const el = document.getElementById('stock-list');
    el.innerHTML = stocks.map(s => `
        <div class="stock-item ${s.symbol === currentSymbol ? 'active' : ''}" data-sym="${s.symbol}">
            <div class="stock-item-left">
                <div class="sym">${s.symbol}</div>
                <div class="co">${s.name.split(' ')[0]}</div>
            </div>
            <div class="stock-item-right">
                <div class="price">$${s.price.toFixed(2)}</div>
                <div class="chg ${s.change_pct >= 0 ? 'positive' : 'negative'}">${s.change_pct >= 0 ? '+' : ''}${s.change_pct}%</div>
            </div>
        </div>
    `).join('');

    el.querySelectorAll('.stock-item').forEach(item => {
        item.addEventListener('click', () => {
            currentSymbol = item.dataset.sym;
            el.querySelectorAll('.stock-item').forEach(i => i.classList.remove('active'));
            item.classList.add('active');
            loadChart(currentSymbol, currentPeriod);
        });
    });
}

// ── Period buttons ───────────────────────────────────────────────────────────
document.querySelectorAll('.period-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentPeriod = btn.dataset.p;
        loadChart(currentSymbol, currentPeriod);
    });
});

// ── Toggle overlays ──────────────────────────────────────────────────────────
document.getElementById('toggle-ma20').addEventListener('change', e => {
    ma20Series.applyOptions({ visible: e.target.checked });
});
document.getElementById('toggle-ma50').addEventListener('change', e => {
    ma50Series.applyOptions({ visible: e.target.checked });
});
document.getElementById('toggle-pred').addEventListener('change', e => {
    predSeries.applyOptions({ visible: e.target.checked });
});

// ── Search ───────────────────────────────────────────────────────────────────
document.getElementById('search-input').addEventListener('input', e => {
    const q = e.target.value.toLowerCase();
    renderStockList(allStocks.filter(s => s.symbol.toLowerCase().includes(q) || s.name.toLowerCase().includes(q)));
});

// ── Helpers ──────────────────────────────────────────────────────────────────
function fmtVol(v) {
    if (v >= 1e9) return (v / 1e9).toFixed(1) + 'B';
    if (v >= 1e6) return (v / 1e6).toFixed(1) + 'M';
    if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K';
    return v;
}

// ── Boot ─────────────────────────────────────────────────────────────────────
initChart();
loadStockList();
loadChart(currentSymbol, currentPeriod);
