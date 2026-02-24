from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import httpx
import time
from datetime import datetime

app = FastAPI()

async def get_test_balance():
    return {
        "total": 12500.50,
        "usdt": 10000.25,
        "btc": 0.125,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/balance")
async def api_balance():
    return await get_test_balance()

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        symbol = data.get("symbol", "UNKNOWN")
        action = data.get("action", "unknown").upper()
        price = data.get("price", 0)
        
        print(f"🔔 {symbol} {action} ${price}")
        
        # 🔥 AUTO EXECUTE (Test Mode)
        if action == "BUY":
            print(f"✅ SIMULATED BUY: {symbol} @ ${price}")
        elif action == "SELL":
            print(f"✅ SIMULATED SELL: {symbol} @ ${price}")
        elif action == "TEST":
            print(f"🧪 TEST OK: {symbol}")
            
        return {"status": "executed", "symbol": symbol, "action": action}
    except Exception as e:
        print(f"❌ Error: {e}")
        return {"status": "error"}

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trading Bot Pro</title>
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://unpkg.com/htmx.org@1.9.10"></script>
</head>
<body class="bg-gradient-to-br from-indigo-900 to-purple-900 min-h-screen p-6 text-white">
<div class="max-w-4xl mx-auto">
<h1 class="text-4xl font-bold text-center mb-8">🚀 Trading Bot Pro</h1>

<div class="bg-white/10 backdrop-blur p-8 rounded-3xl mb-8 text-center" 
hx-get="/api/balance" hx-trigger="load, every 5s" hx-target="#balance">
<div id="balance" class="text-xl">جاري التحميل...</div>
</div>

<div class="grid grid-cols-2 gap-4 mb-8">
<button class="bg-green-500 hover:bg-green-600 p-4 rounded-xl font-bold" onclick="testBuy()">🟢 شراء</button>
<button class="bg-red-500 hover:bg-red-600 p-4 rounded-xl font-bold" onclick="testSell()">🔴 بيع</button>
</div>

<div class="bg-green-500/20 p-6 rounded-2xl text-center">
<p>✅ Webhook: https://tradbot-2qlz.onrender.com/webhook</p>
<p class="text-sm mt-2 text-green-300">آخر تحديث: <span id="time"></span></p>
</div>
</div>

<script>
document.body.addEventListener('htmx:afterSwap', e => {
    if(e.detail.target.id === 'balance') {
        try {
            const d = JSON.parse(e.detail.xhr.responseText);
            e.detail.target.innerHTML = `
                <div class="text-3xl font-bold text-green-400 mb-4">$${d.total?.toLocaleString()}</div>
                <div>USDT: <span class="text-green-400">${d.usdt?.toFixed(2)}</span></div>
                <div>BTC: <span class="text-orange-400">${d.btc?.toFixed(6)}</span></div>
            `;
        } catch(err) {}
    }
});

function testBuy() { alert('🟢 SIMULATED BUY OK!'); }
function testSell() { alert('🔴 SIMULATED SELL OK!'); }
function updateTime() { document.getElementById('time').textContent = new Date().toLocaleTimeString('ar-SA'); }
updateTime(); setInterval(updateTime, 1000);
</script>
</body>
</html>
"""
    return HTMLResponse(content=html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
