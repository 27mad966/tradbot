from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import json
import os
import hmac
import hashlib
import time
import requests
from datetime import datetime

app = FastAPI(title="Trading Bot Pro v8.1 - Binance Testnet")

# ===== ضع API Keys هنا =====
BINANCE_API_KEY = "OiPl7xWT2zOuZMu2for53DDmJvludenpCiIOghBW4KKfQksOwCOHZmVCUsGeQCI3"
BINANCE_SECRET_KEY = "D83WGpMFTUOl38r6VdeUlEJfVx32YHIVSFFCGp4qXnMOZMuNyV0WScZH2gP09BeI"

TRADES_FILE = "trades.json"

def binance_signed_request(method, endpoint, params=None):
    timestamp = int(time.time() * 1000)
    params = params or {}
    params['timestamp'] = timestamp
    query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(BINANCE_SECRET_KEY.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    params['signature'] = signature
    
    url = f"https://testnet.binance.vision/api{endpoint}"
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    response = requests.request(method, url, headers=headers, params=params)
    return response.json()

def get_balance():
    try:
        account = binance_signed_request('GET', '/v3/account')
        balances = {}
        for b in account.get('balances', []):
            free = float(b.get('free', 0))
            if free > 0.01:
                balances[b['asset']] = free
        return balances
    except:
        return {'USDT': 10000.0}

def place_order(symbol, side, quantity):
    params = {
        'symbol': symbol,
        'side': side,
        'type': 'MARKET',
        'quantity': f"{quantity:.3f}"
    }
    try:
        return binance_signed_request('POST', '/v3/order', params)
    except Exception as e:
        return {'error': str(e)}

def load_trades():
    try:
        if os.path.exists(TRADES_FILE):
            with open(TRADES_FILE) as f:
                trades = json.load(f)
                return trades[-15:] if isinstance(trades, list) else []
    except:
        pass
    return []

def save_trade(trade):
    trades = load_trades()
    trades.append(trade)
    try:
        with open(TRADES_FILE, 'w') as f:
            json.dump(trades, f, indent=2)
    except:
        pass

@app.get("/api/balance")
async def api_balance():
    balances = get_balance()
    total_usdt = balances.get('USDT', 0)
    if 'BTC' in balances:
        total_usdt += balances['BTC'] * 95000
    return {"balances": balances, "total_usdt": total_usdt}

@app.get("/api/trades")
async def api_trades():
    trades = load_trades()
    return {"trades": trades, "count": len(trades)}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        symbol = data.get("symbol", "BTCUSDT").upper()
        action = data.get("action", "BUY").upper()
        price = float(data.get("price", 0)) or None
        amount_usdt = float(data.get("amount", 10))
        
        side = "BUY" if action in ["BUY", "LONG"] else "SELL"
        
        # Market order
        order_result = place_order(symbol, side, amount_usdt / 95000)
        
        trade = {
            "time": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "action": action,
            "side": side,
            "price": price or 95000,
            "amount": amount_usdt,
            "order_id": order_result.get('orderId'),
            "status": order_result.get('status', 'unknown')
        }
        
        save_trade(trade)
        return {"status": "OK", "trade": trade, "order": order_result}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}

@app.get("/ping")
async def ping():
    return {"status": "alive"}

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    balances = get_balance()
    
    html_template = """
<!DOCTYPE html>
<html dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width">
<title>Trading Bot Pro v8.1 - Binance Testnet</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:Tahoma,Arial,sans-serif;background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);color:#fff;padding:20px;min-height:100vh}}
.container{{max-width:1400px;margin:0 auto}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:25px}}
.card{{background:rgba(15,15,35,0.95);backdrop-filter:blur(20px);border-radius:20px;padding:30px;border:1px solid rgba(0,212,170,0.3);box-shadow:0 20px 40px rgba(0,0,0,0.5)}}
h3{{color:#00d4aa;margin-bottom:20px;font-size:1.4em;font-weight:700;border-bottom:2px solid rgba(0,212,170,0.3);padding-bottom:15px}}
.balance-list{{max-height:300px;overflow-y:auto}}
.balance-item{{display:flex;justify-content:space-between;padding:15px 0;border-bottom:1px solid rgba(255,255,255,0.1);font-size:1.1em}}
.balance-item:last-child{{border-bottom:none}}
.balance-value.positive{{color:#00d4aa;font-weight:600}}
.balance-value.negative{{color:#ff6b6b}}
table{{width:100%;border-collapse:collapse;font-size:0.95em;margin-top:20px}}
th,td{{padding:15px 12px;text-align:right;border-bottom:1px solid rgba(255,255,255,0.1)}}
th{{background:linear-gradient(90deg,#16213e,#1a1a2e);color:#00d4aa;font-weight:600}}
.symbol{{color:#00d4aa;font-weight:700;font-size:1.1em}}
tr:hover{{background:rgba(0,212,170,0.1)}}
.status-bar{{background:rgba(22,33,62,0.9);border-radius:15px;padding:20px;margin-top:25px;text-align:center;font-size:1em;border:1px solid rgba(0,212,170,0.3)}}
button{{background:linear-gradient(135deg,#00d4aa,#00a085);color:#fff;border:none;padding:15px 30px;border-radius:12px;cursor:pointer;margin:10px;font-weight:700;font-size:1.1em;transition:all 0.3s;box-shadow:0 5px 15px rgba(0,212,170,0.3)}}
button:hover{{transform:translateY(-3px);box-shadow:0 10px 25px rgba(0,212,170,0.5)}}
.quick-trade{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin:20px 0}}
@media(max-width:768px){{.grid{{grid-template-columns:1fr}}.quick-trade{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<div class="container">
<div class="grid">
<div class="card">
<h3>💰 رصيد الحساب - Binance Testnet</h3>
<div class="balance-list" id="balance-list">
    جاري تحميل الرصيد...
</div>
</div>
<div class="card">
<h3>🧪 تداول سريع</h3>
<div class="quick-trade">
    <button onclick="quickTrade('BTCUSDT', 'BUY', 10)">🟢 شراء BTC $10</button>
    <button onclick="quickTrade('BTCUSDT', 'SELL', 10)">🔴 بيع BTC $10</button>
    <button onclick="quickTrade('ETHUSDT', 'BUY', 10)">🟢 شراء ETH $10</button>
    <button onclick="quickTrade('ETHUSDT', 'SELL', 10)">🔴 بيع ETH $10</button>
</div>
<button onclick="location.reload()" style="width:100%">🔄 تحديث كامل</button>
</div>
<div class="card" style="grid-column:1/-1">
<h3>📈 سجل الصفقات</h3>
<div id="trades-container">جاري تحميل الصفقات...</div>
</div>
</div>
<div class="status-bar">
<span>🚀 Trading Bot v8.1</span> | 
<span id="status">متصل ✅</span> | 
<span>آخر تحديث: <span id="last-update">--:--</span></span>
</div>
</div>
<script>
let lastUpdate = new Date();
document.getElementById('last-update').textContent = lastUpdate.toLocaleTimeString('ar-SA');

async function updateDashboard() {
    try {
        const [balanceRes, tradesRes] = await Promise.all([
            fetch('/api/balance'),
            fetch('/api/trades')
        ]);
        
        const balances = await balanceRes.json();
        const tradesData = await tradesRes.json();
        
        // Update balances
        let balanceHtml = '';
        Object.entries(balances.balances).sort(([,a],[,b])=>b-a).slice(0,10).forEach(([asset, amount]) => {
            const valueClass = amount > 1 ? 'positive' : '';
            balanceHtml += `<div class="balance-item">
                <span>${asset}</span>
                <span class="balance-value ${valueClass}">${amount.toFixed(4)}</span>
            </div>`;
        });
        document.getElementById('balance-list').innerHTML = balanceHtml || 'لا توجد أرصدة';
        
        // Update trades
        const tradesContainer = document.getElementById('trades-container');
        if (tradesData.trades.length === 0) {
            tradesContainer.innerHTML = '<div style="text-align:center;padding:40px;color:#888">لا توجد صفقات بعد<br><small>اضغط أي زر تداول للبدء</small></div>';
        } else {
            let tableHtml = '<table><thead><tr><th>الوقت</th><th>الرمز</th><th>النوع</th><th>السعر</th><th>الكمية</th><th>رقم الطلب</th><th>الحالة</th></tr></thead><tbody>';
            tradesData.trades.forEach(trade => {
                tableHtml += `<tr>
                    <td>${new Date(trade.time).toLocaleString('ar-SA')}</td>
                    <td class="symbol">${trade.symbol}</td>
                    <td style="color:${trade.side === 'BUY' ? '#00d4aa' : '#ff6b6b'}">${trade.action}</td>
                    <td>$${trade.price.toFixed(2)}</td>
                    <td>${trade.amount ? trade.amount.toFixed(2) : '---'}</td>
                    <td>${trade.order_id || '---'}</td>
                    <td>${trade.status || 'جاري التنفيذ'}</td>
                </tr>`;
            });
            tableHtml += '</tbody></table>';
            tradesContainer.innerHTML = tableHtml;
        }
        
        lastUpdate = new Date();
        document.getElementById('last-update').textContent = lastUpdate.toLocaleTimeString('ar-SA');
        
    } catch(error) {
        console.error('خطأ:', error);
        document.getElementById('status').textContent = '❌ خطأ';
        document.getElementById('status').style.color = '#ff6b6b';
    }
}

async function quickTrade(symbol, action, amount) {
    try {
        const response = await fetch('/webhook', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                symbol: symbol,
                action: action,
                amount: amount
            })
        });
        const result = await response.json();
        if (result.status === 'OK') {
            alert(`✅ تم تنفيذ ${action} ${symbol} بقيمة $${amount}`);
        } else {
            alert(`❌ خطأ: ${result.error || 'فشل التنفيذ'}`);
        }
        updateDashboard();
    } catch(error) {
        alert('❌ خطأ في الاتصال');
    }
}

// تحديث تلقائي كل 3 ثواني
updateDashboard();
setInterval(updateDashboard, 3000);
</script>
</body>
</html>"""
    
    return HTMLResponse(content=html_template)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
