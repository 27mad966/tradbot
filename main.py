from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
                return json.load(f)
        return default or {}
    except:
        return default or {}

def save_json(file, data):
    try:
        with open(file, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except:
        return False

def load_trades():
    return load_json(TRADES_FILE, [])[-50:]

def save_trade(trade):
    trades = load_trades()
    trades.append(trade)
    save_json(TRADES_FILE, trades)

def update_portfolio(symbol, action, qty, price):
    pf = load_json(PORTFOLIO_FILE, {"USDT": 10000, "positions": {}})
    
    if action == "BUY":
        cost = qty * price
        if pf["USDT"] >= cost:
            pf["USDT"] = round(pf["USDT"] - cost, 2)
            pf["positions"][symbol] = round(pf["positions"].get(symbol, 0) + qty, 3)
    elif action == "SELL" and symbol in pf["positions"]:
        pf["positions"][symbol] = max(0, round(pf["positions"][symbol] - qty, 3))
        pf["USDT"] = round(pf["USDT"] + qty * price, 2)
    
    pf["positions"] = {k: v for k, v in pf["positions"].items() if v > 0}
    save_json(PORTFOLIO_FILE, pf)
    return pf

@app.get("/api/portfolio")
async def get_portfolio():
    pf = load_json(PORTFOLIO_FILE)
    cash = pf.get("USDT", 10000)
    positions_value = sum(pf.get("positions", {}).values()) * 100
    total = cash + positions_value
    return {
        "cash": cash,
        "positions_value": positions_value,
        "total": total,
        "positions": pf.get("positions", {})
    }

@app.get("/api/trades")
async def get_trades():
    trades = load_trades()
    total_profit = sum(t.get('profit', 0) for t in trades)
    return {
        "trades": trades[-15:],
        "total_profit": total_profit,
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
        profit = round(qty * (random.uniform(0.95, 1.1) - 1) * price, 2)
        
        trade = {
            "time": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "action": action,
            "price": price,
            "qty": qty,
            "profit": profit
        }
        
        save_trade(trade)
        return {"status": "OK", "trade": trade}
    except:
        return {"status": "ERROR"}

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
<title>Trading Bot Pro v7.3</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Tahoma, Arial, sans-serif;background:#1a1a2e;color:#fff;padding:20px;line-height:1.6}
.container{max-width:1200px;margin:0 auto}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
.card{background:#0f0f23;border-radius:10px;padding:25px;border:1px solid #333}
h3{color:#00D4AA;margin-bottom:15px;font-size:1.2em}
.metric{display:flex;justify-content:space-between;align-items:center;padding:15px;background:#1a1a2e;border-radius:8px;margin:10px 0}
.metric-value{font-size:1.4em;font-weight:bold}
.profit{color:#00D4AA}
.loss{color:#ff4444}
table{width:100%;border-collapse:collapse;font-size:0.9em;margin-top:15px}
th,td{padding:12px 8px;text-align:right;border-bottom:1px solid #333}
th{background:#16213e;font-weight:bold}
.symbol{color:#00D4AA;font-weight:bold;font-size:1em}
tr:hover{background:rgba(0,212,170,0.1)}
button{background:#00D4AA;color:#fff;border:none;padding:12px 24px;border-radius:6px;cursor:pointer;margin:5px;font-weight:bold;font-size:1em}
button:hover{background:#00A085;transform:translateY(-1px)}
.status{padding:15px;background:#16213e;border-radius:10px;margin-top:20px;text-align:center;font-size:0.9em}
@media(max-width:768px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="container">
<div class="grid">
<div class="card">
<h3>💰 حالة المحفظة</h3>
<div class="metric"><span>الإجمالي:</span><span class="metric-value" id="total">$10,000</span></div>
<div class="metric"><span>النقد USDT:</span><span class="metric-value" id="cash">$10,000</span></div>
<div class="metric"><span>قيمة المراكز:</span><span class="metric-value" id="positions">$0</span></div>
</div>
<div class="card">
<h3>📊 الإحصائيات</h3>
<div class="metric"><span>عدد الصفقات:</span><span class="metric-value" id="count">0</span></div>
<div class="metric"><span>إجمالي الربح:</span><span class="metric-value profit" id="profit">$0.00</span></div>
</div>
</div>
<div class="card">
<h3>📈 آخر 15 صفقة</h3>
<button onclick="testTrade()">🧪 اختبار صفقة</button>
<button onclick="location.reload()">🔄 تحديث يدوي</button>
<table>
<thead>
<tr><th>الوقت</th><th>الرمز</th><th>النوع</th><th>السعر</th><th>الكمية</th><th>الربح</th></tr>
</thead>
<tbody id="trades"></tbody>
</table>
</div>
<div class="status">
حالة الخادم: <span style="color:#00D4AA">✅ متصل</span> | 
التحديث: <span id="last-update">الآن</span> | 
الصفقات المحفوظة: <span id="saved-count">0</span>
</div>
</div>

<script>
let lastUpdate = new Date();
document.getElementById('last-update').textContent = lastUpdate.toLocaleTimeString('ar');

async function updateDashboard() {
    try {
        const [portfolioRes, tradesRes] = await Promise.all([
            fetch('/api/portfolio'),
            fetch('/api/trades')
        ]);
        
        const portfolio = await portfolioRes.json();
        const tradesData = await tradesRes.json();
        
        // Update portfolio
        document.getElementById('total').textContent = '$' + portfolio.total.toLocaleString();
        document.getElementById('cash').textContent = '$' + portfolio.cash.toLocaleString();
        document.getElementById('positions').textContent = '$' + portfolio.positions_value.toLocaleString();
        
        // Update stats
        document.getElementById('count').textContent = tradesData.count;
        document.getElementById('profit').textContent = '$' + tradesData.total_profit.toLocaleString('en', {minimumFractionDigits: 2});
        document.getElementById('saved-count').textContent = tradesData.count;
        
        // Update trades table
        const tbody = document.getElementById('trades');
        tbody.innerHTML = tradesData.trades.map(trade => {
            const profitClass = trade.profit > 0 ? 'profit' : 'loss';
            const profitColor = trade.profit > 0 ? '#00D4AA' : '#ff4444';
            return `
                <tr>
                    <td>${new Date(trade.time).toLocaleString('ar-SA', {hour12: false})}</td>
                    <td class="symbol">${trade.symbol}</td>
                    <td>${trade.action}</td>
                    <td style="color:#00D4AA;">$${trade.price.toFixed(2)}</td>
                    <td>${trade.qty.toFixed(3)}</td>
                    <td style="color:${profitColor};font-weight:bold;">$${trade.profit.toFixed(2)}</td>
                </tr>
            `;
        }).join('');
        
        lastUpdate = new Date();
        document.getElementById('last-update').textContent = lastUpdate.toLocaleTimeString('ar');
        
    } catch(error) {
        console.error('خطأ في التحديث:', error);
    }
}

async function testTrade() {
    const symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'];
    const symbol = symbols[Math.floor(Math.random() * symbols.length)];
    
    try {
        const response = await fetch('/webhook', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                symbol: symbol,
                action: Math.random() > 0.5 ? 'BUY' : 'SELL',
                price: 100 + Math.random() * 100,
                amount: 5 + Math.random() * 20
            })
        });
        
        if (response.ok) {
            alert('✅ تمت إضافة صفقة تجريبية: ' + symbol);
            updateDashboard();
        }
    } catch(error) {
        alert('❌ خطأ في تنفيذ الصفقة');
    }
}

// بدء التحديث التلقائي
updateDashboard();
setInterval(updateDashboard, 3000);
</script>
</body>
</html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
