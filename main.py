from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import json
import os
import random
from datetime import datetime

app = FastAPI()

TRADES_FILE = "trades.json"
PORTFOLIO_FILE = "portfolio.json"

def load_json(file, default={}):
    try:
        if os.path.exists(file):
            with open(file) as f:
                return json.load(f)
        return default
    except:
        return default

def save_json(file, data):
    try:
        with open(file, 'w') as f:
            json.dump(data, f, indent=2)
    except:
        pass

def load_trades():
    trades = load_json(TRADES_FILE, [])
    return trades[-100:]

def save_trade(trade):
    trades = load_trades()
    trades.append(trade)
    save_json(TRADES_FILE, trades)

def update_portfolio(symbol, action, qty, price):
    pf = load_json(PORTFOLIO_FILE, {"USDT": 10000, "positions": {}})
    if action == "BUY":
        cost = qty * price
        if pf["USDT"] >= cost:
            pf["USDT"] -= cost
            pf["positions"][symbol] = pf["positions"].get(symbol, 0) + qty
    elif action == "SELL":
        if symbol in pf["positions"]:
            pf["positions"][symbol] = max(0, pf["positions"][symbol] - qty)
            pf["USDT"] += qty * price
    pf["positions"] = {k: v for k, v in pf["positions"].items() if v > 0}
    save_json(PORTFOLIO_FILE, pf)
    return pf

@app.get("/api/portfolio")
async def api_portfolio():
    pf = load_json(PORTFOLIO_FILE)
    total = pf.get("USDT", 10000)
    for sym, qty in pf.get("positions", {}).items():
        total += qty * 100
    return {"cash": pf.get("USDT", 10000), "total": total, "positions": pf.get("positions", {})}

@app.get("/api/trades")
async def api_trades():
    trades = load_trades()
    profit = sum(t.get('profit', 0) for t in trades)
    return {"trades": trades[-15:], "profit": profit, "count": len(trades)}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    sym = data.get("symbol", "BTCUSDT")
    act = data.get("action", "BUY")
    price = data.get("price", 100)
    qty = data.get("amount", 10)
    
    pf = update_portfolio(sym, act, qty, price)
    profit = qty * price * random.uniform(-0.05, 0.15)
    
    trade = {
        "time": datetime.utcnow().isoformat(),
        "symbol": sym,
        "action": act,
        "price": price,
        "qty": qty,
        "profit": profit
    }
    save_trade(trade)
    return {"status": "OK", "trade": trade}

@app.get("/ping")
async def ping():
    return {"status": "alive"}

@app.get("/")
async def dashboard():
    portfolio = load_json(PORTFOLIO_FILE)
    trades = load_trades()[-10:]
    
    css = """
    *{margin:0;padding:0;box-sizing:border-box}
    body{font-family:Arial;background:#1a1a2e;color:#fff;padding:20px;line-height:1.5}
    .container{max-width:1200px;margin:0 auto}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
    .card{background:#0f0f23;border-radius:10px;padding:25px;border:1px solid #333}
    h3{color:#00D4AA;margin-bottom:15px;font-size:1.2em}
    .metric{display:flex;justify-content:space-between;padding:15px;background:#1a1a2e;border-radius:8px;margin:10px 0}
    .metric-value{font-size:1.4em;font-weight:bold}
    .profit{color:#00D4AA}
    .loss{color:#ff4444}
    table{width:100%;border-collapse:collapse;font-size:0.9em}
    th,td{padding:10px 8px;text-align:right;border-bottom:1px solid #333}
    th{background:#16213e;font-weight:bold}
    .symbol{color:#00D4AA;font-weight:bold}
    tr:hover{background:rgba(0,212,170,0.1)}
    button{background:#00D4AA;color:#fff;border:none;padding:10px 20px;border-radius:6px;cursor:pointer;margin:5px;font-weight:bold}
    button:hover{background:#00A085}
    @media(max-width:768px){.grid{grid-template-columns:1fr}}
    """
    
    trades_html = ""
    for t in trades:
        p = t.get('profit', 0)
        cls = "profit" if p > 0 else "loss"
        trades_html += f'<tr><td>{t.get("time","N/A")[:16]}</td><td class="symbol">{t.get("symbol","N/A")}</td><td>{t.get("action","N/A")}</td><td>${t.get("price",0):.2f}</td><td>{t.get("qty",0):.2f}</td><td class="{cls}">${p:.2f}</td></tr>'
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width">
<title>Trading Bot v7.2</title>
<style>{css}</style>
</head>
<body>
<div class="container">
<div class="grid">
<div class="card">
<h3>💰 المحفظة</h3>
<div class="metric"><span>الإجمالي:</span><span class="metric-value" id="total">$10,000</span></div>
<div class="metric"><span>نقد USDT:</span><span class="metric-value" id="cash">$10,000</span></div>
<div class="metric"><span>المراكز:</span><span class="metric-value" id="positions">{{0}}</span></div>
</div>
<div class="card">
<h3>📊 الإحصائيات</h3>
<div class="metric"><span>الصفقات:</span><span class="metric-value" id="count">0</span></div>
<div class="metric"><span>الربح:</span><span class="metric-value profit" id="profit">$0</span></div>
</div>
</div>
<div class="card">
<h3>📈 آخر الصفقات</h3>
<button onclick="testTrade()">🧪 اختبار صفقة</button>
<button onclick="location.reload()">🔄 تحديث</button>
<table>
<thead><tr><th>الوقت</th><th>الرمز</th><th>النوع</th><th>السعر</th><th>الكمية</th><th>الربح</th></tr></thead>
<tbody id="table">{trades_html}</tbody>
</table>
</div>
<div style="text-align:center;padding:20px;background:#16213e;border-radius:10px;margin-top:20px;font-size:0.9em">
حالة الخادم: <span style="color:#00D4AA">متصل ✅</span> | تحديث كل 3 ثواني
</div>
</div>
<script>
async function updateData() {{
    try {{
        const pf = await (await fetch('/api/portfolio')).json();
        const tr = await (await fetch('/api/trades')).json();
        
        document.getElementById('total').textContent = '$' + pf.total.toLocaleString();
        document.getElementById('cash').textContent = '$' + pf.cash.toLocaleString();
        document.getElementById('count').textContent = tr.count;
        document.getElementById('profit').textContent = '$' + tr.profit.toLocaleString();
        
        document.querySelector('#table').innerHTML = tr.trades.map(t => 
            `<tr><td>${{t.time.slice(0,16)}}</td><td class=symbol>${{t.symbol}}</td><td>${{t.action}}</td><td>$${t.price.toFixed(2)}</td><td>${t.qty.toFixed(2)}</td><td class=${{t.profit>0?'profit':'loss'}}>$${t.profit.toFixed(2)}</td></tr>`
        ).join('');
    }} catch(e) {{ console.log('Error:', e); }}
}}

async function testTrade() {{
    const symbols = ['BTCUSDT','ETHUSDT','SOLUSDT'];
    await fetch('/webhook', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{
            symbol: symbols[Math.floor(Math.random()*symbols.length)],
            action: Math.random()>0.5 ? 'BUY' : 'SELL',
            price: 100 + Math.random()*100,
            amount: 5 + Math.random()*20
        }})
    }});
    updateData();
}}

updateData();
setInterval(updateData, 3000);
</script>
</body>
</html>
    """
    return HTMLResponse(html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
