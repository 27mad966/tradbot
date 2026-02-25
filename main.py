from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import json
import os
import random
from datetime import datetime

app = FastAPI()

TRADES_FILE = "trades.json"
PORTFOLIO_FILE = "portfolio.json"

def load_json(file, default=None):
    try:
        if os.path.exists(file):
            with open(file) as f:
                data = json.load(f)
                return data if data is not None else (default or {})
        return default or {}
    except:
        return default or []

def save_json(file, data):
    try:
        os.makedirs(os.path.dirname(file) or '.', exist_ok=True)
        with open(file, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except:
        return False

def load_trades():
    trades = load_json(TRADES_FILE, [])
    if isinstance(trades, list):
        return trades[-50:]
    return []

def save_trade(trade):
    trades = load_trades()
    trades.append(trade)
    save_json(TRADES_FILE, trades)

def update_portfolio(symbol, action, qty, price):
    pf = load_json(PORTFOLIO_FILE, {"USDT": 10000, "positions": {}})
    if action == "BUY":
        cost = qty * price
        if pf.get("USDT", 0) >= cost:
            pf["USDT"] = round(pf["USDT"] - cost, 2)
            pf.setdefault("positions", {})[symbol] = round(pf["positions"].get(symbol, 0) + qty, 3)
    elif action == "SELL":
        positions = pf.setdefault("positions", {})
        if symbol in positions:
            positions[symbol] = max(0, round(positions[symbol] - qty, 3))
            pf["USDT"] = round(pf.get("USDT", 0) + qty * price, 2)
            if positions[symbol] == 0:
                del positions[symbol]
    
    save_json(PORTFOLIO_FILE, pf)
    return pf

@app.get("/api/portfolio")
async def get_portfolio():
    pf = load_json(PORTFOLIO_FILE, {"USDT": 10000, "positions": {}})
    cash = pf.get("USDT", 10000)
    positions_value = sum(pf.get("positions", {}).values()) * 100
    return {
        "cash": round(cash, 2),
        "positions_value": round(positions_value, 2),
        "total": round(cash + positions_value, 2)
    }

@app.get("/api/trades")
async def get_trades():
    trades = load_trades()
    total_profit = sum(float(t.get('profit', 0)) for t in trades)
    return {
        "trades": trades,
        "total_profit": round(total_profit, 2),
        "count": len(trades)
    }

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        symbol = data.get("symbol", "BTCUSDT")
        action = data.get("action", "BUY")
        price = float(data.get("price", 100))
        qty = float(data.get("amount", 10))
        
        pf = update_portfolio(symbol, action, qty, price)
        profit = round(qty * price * random.uniform(-0.05, 0.12), 2)
        
        trade = {
            "time": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "action": action,
            "price": round(price, 2),
            "qty": round(qty, 3),
            "profit": profit
        }
        
        save_trade(trade)
        return {"status": "OK", "message": f"تم تنفيذ {action} {symbol}"}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}

@app.get("/ping")
async def ping():
    return {"status": "alive"}

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>
<html dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width">
<title>🚀 Trading Bot Pro v7.4</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Tahoma,Arial,sans-serif;background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:20px}
.container{max-width:1200px;margin:0 auto}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
.card{background:rgba(15,15,35,0.8);backdrop-filter:blur(10px);border-radius:15px;padding:30px;border:1px solid #00D4AA20;box-shadow:0 10px 30px rgba(0,0,0,0.5)}
h3{color:#00D4AA;margin-bottom:20px;font-size:1.3em;border-bottom:1px solid #00D4AA20;padding-bottom:10px}
.metric{display:flex;justify-content:space-between;padding:20px;background:rgba(26,26,46,0.8);border-radius:10px;margin:10px 0;border:1px solid #333}
.metric-label{font-size:0.95em;opacity:0.9}
.metric-value{font-size:1.6em;font-weight:bold}
.profit{color:#00D4AA}
.loss{color:#ff6b6b}
table{width:100%;border-collapse:collapse;font-size:0.9em;margin-top:20px}
th,td{padding:15px 10px;text-align:right;border-bottom:1px solid #333}
th{background:linear-gradient(90deg,#16213e,#1a1a2e);font-weight:bold;color:#00D4AA}
.symbol{color:#00D4AA;font-weight:bold;font-size:1.1em}
tr:hover{background:rgba(0,212,170,0.1)}
button{background:linear-gradient(135deg,#00D4AA,#00A085);color:#fff;border:none;padding:15px 30px;border-radius:10px;cursor:pointer;margin:10px 5px;font-weight:bold;font-size:1em;transition:all 0.3s}
button:hover{transform:translateY(-3px);box-shadow:0 10px 25px rgba(0,212,170,0.4)}
.status{background:rgba(22,33,62,0.9);border-radius:12px;padding:20px;margin-top:25px;text-align:center;font-size:0.95em;border:1px solid #00D4AA30}
.status span{color:#00D4AA;font-weight:bold}
@media(max-width:768px){.grid{grid-template-columns:1fr}.metric{flex-direction:column;text-align:center;gap:10px}}
</style>
</head>
<body>
<div class="container">
<div class="grid">
<div class="card">
<h3>💰 حالة المحفظة</h3>
<div class="metric">
<span class="metric-label">الإجمالي:</span>
<span class="metric-value profit" id="total">$10,000</span>
</div>
<div class="metric">
<span class="metric-label">النقد USDT:</span>
<span class="metric-value" id="cash">$10,000</span>
</div>
<div class="metric">
<span class="metric-label">قيمة المراكز:</span>
<span class="metric-value" id="positions">$0</span>
</div>
</div>
<div class="card">
<h3>📊 الإحصائيات</h3>
<div class="metric">
<span class="metric-label">إجمالي الصفقات:</span>
<span class="metric-value" id="count">0</span>
</div>
<div class="metric">
<span class="metric-label">صافي الربح:</span>
<span class="metric-value profit" id="profit">$0.00</span>
</div>
</div>
</div>
<div class="card">
<h3>📈 آخر 15 صفقة</h3>
<button onclick="testTrade()">🧪 اختبار صفقة</button>
<button onclick="location.reload()">🔄 تحديث يدوي</button>
<table>
<thead><tr><th>الوقت</th><th>الرمز</th><th>النوع</th><th>السعر</th><th>الكمية</th><th>الربح $</th></tr></thead>
<tbody id="trades"></tbody>
</table>
</div>
<div class="status">
حالة الخادم: <span>✅ نشط</span> | 
آخر تحديث: <span id="last-update">--:--</span> | 
الصفقات المحفوظة: <span id="saved-count">0</span>
</div>
</div>
<script>
let lastUpdateTime = new Date();
document.getElementById('last-update').textContent = lastUpdateTime.toLocaleTimeString('ar-SA');

async function updateDashboard() {
    try {
        const [portfolioRes, tradesRes] = await Promise.all([fetch('/api/portfolio'), fetch('/api/trades')]);
        const portfolio = await portfolioRes.json();
        const tradesData = await tradesRes.json();
        
        document.getElementById('total').textContent = '$' + portfolio.total.toLocaleString();
        document.getElementById('cash').textContent = '$' + portfolio.cash.toLocaleString();
        document.getElementById('positions').textContent = '$' + portfolio.positions_value.toLocaleString();
        
        document.getElementById('count').textContent = tradesData.count;
        document.getElementById('profit').textContent = '$' + tradesData.total_profit.toLocaleString('en', {minimumFractionDigits: 2, maximumFractionDigits: 2});
        document.getElementById('saved-count').textContent = tradesData.count;
        
        const tbody = document.getElementById('trades');
        tbody.innerHTML = tradesData.trades.map(trade => {
            const isProfit = trade.profit > 0;
            return `
                <tr>
                    <td>${new Date(trade.time).toLocaleString('ar-SA', {hour12: false})}</td>
                    <td class="symbol">${trade.symbol}</td>
                    <td>${trade.action}</td>
                    <td style="color:#00D4AA;font-weight:bold;">$${trade.price.toFixed(2)}</td>
                    <td>${trade.qty.toFixed(3)}</td>
                    <td style="color:${isProfit ? '#00D4AA' : '#ff6b6b'};font-weight:bold;font-size:1.1em;">$${trade.profit.toFixed(2)}</td>
                </tr>`;
        }).join('');
        
        lastUpdateTime = new Date();
        document.getElementById('last-update').textContent = lastUpdateTime.toLocaleTimeString('ar-SA');
        
    } catch(error) {
        console.error('خطأ:', error);
    }
}

async function testTrade() {
    const symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'];
    const symbol = symbols[Math.floor(Math.random() * symbols.length)];
    
    try {
        const response = await fetch('/webhook', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                symbol: symbol,
                action: Math.random() > 0.5 ? 'BUY' : 'SELL',
                price: (80 + Math.random() * 120),
                amount: (5 + Math.random() * 25)
            })
        });
        
        if (response.ok) {
            alert(`✅ تمت إضافة صفقة: ${symbol}`);
            updateDashboard();
        } else {
            alert('❌ خطأ في التنفيذ');
        }
    } catch(e) {
        alert('❌ خطأ في الاتصال');
    }
}

updateDashboard();
setInterval(updateDashboard, 3000);
</script>
</body>
</html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
