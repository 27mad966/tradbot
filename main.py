from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
import json
import os
import hmac
import hashlib
import time
from datetime import datetime
import requests

app = FastAPI(title="🚀 Trading Bot Pro v8.0 - Binance Testnet")

# ===== Binance Testnet API Keys (ضعها هنا) =====
BINANCE_API_KEY = "OiPl7xWT2zOuZMu2for53DDmJvludenpCiIOghBW4KKfQksOwCOHZmVCUsGeQCI3"
BINANCE_SECRET_KEY = "D83WGpMFTUOl38r6VdeUlEJfVx32YHIVSFFCGp4qXnMOZMuNyV0WScZH2gP09BeI"
BINANCE_TESTNET = True  # True = Testnet, False = Mainnet

TRADES_FILE = "trades.json"
PORTFOLIO_FILE = "portfolio.json"

def binance_request(method, endpoint, params=None):
    """Binance API request with signature"""
    timestamp = int(time.time() * 1000)
    params = params or {}
    params['timestamp'] = timestamp
    
    query = '&'.join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(
        BINANCE_SECRET_KEY.encode(), 
        query.encode(), 
        hashlib.sha256
    ).hexdigest()
    
    params['signature'] = signature
    url = f"https://testnet.binance.vision/api{endpoint}" if BINANCE_TESTNET else f"https://api.binance.com/api{endpoint}"
    
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    response = requests.request(method, url, headers=headers, params=params)
    return response.json()

def get_balance():
    """Get account balance from Binance"""
    try:
        account = binance_request('GET', '/v3/account')
        balances = {}
        for b in account['balances']:
            if float(b['free']) > 0:
                balances[b['asset']] = float(b['free'])
        return balances
    except:
        return {'USDT': 10000}

def place_order(symbol, side, qty, price=None):
    """Place market/limit order"""
    params = {
        'symbol': symbol,
        'side': side,
        'type': 'MARKET' if not price else 'LIMIT',
        'quantity': str(qty)
    }
    if price:
        params['price'] = str(price)
        params['timeInForce'] = 'GTC'
    
    try:
        result = binance_request('POST', '/v3/order', params)
        return result
    except Exception as e:
        return {'error': str(e)}

def load_json(file, default=None):
    try:
        if os.path.exists(file):
            with open(file) as f:
                return json.load(f)
        return default or []
    except:
        return default or []

def save_json(file, data):
    try:
        with open(file, 'w') as f:
            json.dump(data, f, indent=2)
    except:
        pass

def load_trades():
    trades = load_json(TRADES_FILE, [])
    return trades[-50:] if isinstance(trades, list) else []

@app.get("/api/portfolio")
async def get_portfolio():
    balances = get_balance()
    cash = balances.get('USDT', 0)
    
    # Simulate positions value (BTC price * quantity)
    positions_value = 0
    if 'BTC' in balances:
        positions_value = balances['BTC'] * 95000  # Current BTC price
    
    return {
        "cash": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "total": round(cash + positions_value, 2),
        "balances": balances
    }

@app.get("/api/trades")
async def get_trades():
    trades = load_trades()
    total_profit = sum(float(t.get('profit', 0)) for t in trades)
    return {"trades": trades, "total_profit": round(total_profit, 2), "count": len(trades)}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        symbol = data.get("symbol", "BTCUSDT").upper()
        action = data.get("action", "BUY").upper()
        price = float(data.get("price", 0)) or None
        amount = float(data.get("amount", 10))
        
        # Convert to Binance format
        side = "BUY" if action in ["BUY", "LONG"] else "SELL"
        qty = amount / price if price else amount  # USDT to quantity
        
        # Execute real order
        order_result = place_order(symbol, side, qty, price)
        
        if 'orderId' in order_result:
            trade = {
                "time": datetime.utcnow().isoformat(),
                "symbol": symbol,
                "action": action,
                "side": side,
                "price": price or order_result.get('fills', [{}])[0].get('price', 0),
                "qty": qty,
                "order_id": order_result['orderId'],
                "status": order_result.get('status', 'FILLED')
            }
            save_json(TRADES_FILE, load_trades() + [trade])
            return {"status": "EXECUTED", "order": order_result, "trade": trade}
        else:
            return {"status": "FAILED", "error": order_result}
            
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}

@app.get("/balance")
async def manual_balance():
    return get_balance()

@app.get("/ping")
async def ping():
    return {"status": "alive", "binance": BINANCE_TESTNET}

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    balances = get_balance()
    
    html = f"""
<!DOCTYPE html>
<html dir="rtl">
<head>
<title>🚀 Trading Bot Pro v8.0 - Binance Testnet</title>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{{font-family:Tahoma;background:#1a1a2e;color:#fff;padding:20px}}
.container{{max-width:1400px;margin:0 auto}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}}
.card{{background:rgba(15,15,35,.9);border-radius:15px;padding:25px;border:1px solid #00D4AA30}}
h3{{color:#00D4AA;margin-bottom:15px;font-size:1.3em}}
.metric{{display:flex;justify-content:space-between;padding:15px;background:rgba(26,26,46,.8);border-radius:10px;margin:8px 0}}
table{{width:100%;border-collapse:collapse;font-size:.9em;margin-top:15px}}
th,td{{padding:12px 8px;text-align:right;border-bottom:1px solid #333}}
th{{background:#16213e;color:#00D4AA}}
.symbol{{color:#00D4AA;font-weight:bold}}
button{{background:#00D4AA;color:#fff;border:none;padding:12px 24px;border-radius:8px;cursor:pointer;margin:5px;font-weight:bold}}
button:hover{{background:#00A085}}
@media(max-width:768px){{.grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="container">
<div class="grid">
<div class="card">
<h3>💰 رصيد Binance Testnet</h3>
"""
    
    for asset, amount in list(sorted(balances.items(), key=lambda x: x[1], reverse=True))[:10]:
        html += f'<div class="metric"><span>{asset}</span><span>${amount:.2f}</span></div>'
    
    html += f"""
</div>
<div class="card">
<h3>🧪 التحكم</h3>
<button onclick="testOrder('BTCUSDT','BUY',0.001)">شراء BTC</button>
<button onclick="testOrder('BTCUSDT','SELL',0.001)">بيع BTC</button>
<button onclick="location.reload()">🔄 تحديث</button>
</div>
</div>
<div class="card" style="grid-column:1/-1">
<h3>📈 آخر الصفقات</h3>
<div id="trades-status">جاري التحميل...</div>
</div>
</div>
<script>
async function updateDashboard() {{
    try {{
        const trades = await (await fetch('/api/trades')).json();
        const portfolio = await (await fetch('/api/portfolio')).json();
        
        let table = '<table><tr><th>الوقت</th><th>الرمز</th><th>النوع</th><th>السعر</th><th>الكمية</th><th>الحالة</th></tr>';
        trades.trades.forEach(t => {{
            table += `<tr>
                <td>${{new Date(t.time).toLocaleString('ar')}}</td>
                <td class="symbol">${{t.symbol}}</td>
                <td>${{t.action}}</td>
                <td>$${t.price?.toFixed(2) || '---'}</td>
                <td>${t.qty?.toFixed(3) || '---'}</td>
                <td>${t.status || t.order_id || '---'}</td>
            </tr>`;
        }});
        table += '</table>';
        document.getElementById('trades-status').innerHTML = table;
    }} catch(e) {{ console.error(e); }}
}}

async function testOrder(symbol, side, qty) {{
    await fetch('/webhook', {{
        method: 'POST',
        headers: {{'Content-Type':'application/json'}},
        body: JSON.stringify({{symbol, action: side, amount: qty*60000}})
    }});
    updateDashboard();
}}

updateDashboard();
setInterval(updateDashboard, 3000);
</script>
</body>
</html>
    """
    return HTMLResponse(html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
