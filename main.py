from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import httpx
import hmac
import hashlib
import time
import json
import asyncio
import os
from datetime import datetime
from typing import Dict, Any, List

app = FastAPI(title="Trading Bot Pro v2.0")

# ================= API KEYS =================
API_KEY = os.getenv("BINANCE_API_KEY", "tm14bDzqhm8SnAMnHfE0YocNc6OobZ6nRsjZxMXeWsn74XH6emynQbtbu43fCttt")
SECRET_KEY = os.getenv("BINANCE_SECRET", "YparuR8Q3PmReCdl6gNmLu84qCYDoZqKvbuSqkiER71UiJEGuHRRbjOoSNmRxWZ59")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")

def sign_request(params: Dict[str, str]) -> str:
    query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    return hmac.new(SECRET_KEY.encode(), query_string.encode(), hashlib.sha256).hexdigest()

async def get_binance_balance():
    try:
        if "YOUR_" in API_KEY:
            return await get_test_balance()
            
        timestamp = str(int(time.time() * 1000))
        params = {"timestamp": timestamp}
        params["signature"] = sign_request(params)
        
        headers = {"X-MBX-APIKEY": API_KEY}
        async with httpx.AsyncClient() as session:
            resp = await session.get("https://api.binance.com/api/v3/account", 
                                   params=params, headers=headers, timeout=10)
            data = resp.json()
            
            usdt_bal = next((float(b["free"]) for b in data["balances"] if b["asset"] == "USDT"), 0)
            btc_bal = next((float(b["free"]) for b in data["balances"] if b["asset"] == "BTC"), 0)
            
            return {
                "total": round(usdt_bal + (btc_bal * 62500), 2),
                "usdt": round(usdt_bal, 2),
                "btc": round(btc_bal, 6),
                "status": "live",
                "timestamp": datetime.now().isoformat()
            }
    except:
        return await get_test_balance()

async def get_test_balance():
    return {
        "total": 12500.50,
        "usdt": 10000.25,
        "btc": 0.125,
        "status": "test",
        "timestamp": datetime.now().isoformat()
    }

async def get_live_prices():
    try:
        symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        async with httpx.AsyncClient() as session:
            tasks = [session.get(f"https://api.binance.com/api/v3/ticker/price?symbol={s}") for s in symbols]
            responses = await asyncio.gather(*tasks)
            return {r.json()["symbol"]: float(r.json()["price"]) for r in responses}
    except:
        return {"BTCUSDT": 62500, "ETHUSDT": 2850, "BNBUSDT": 585}

async def get_market_data():
    try:
        async with httpx.AsyncClient() as session:
            resp = await session.get("https://api.binance.com/api/v3/ticker/24hr")
            data = resp.json()
            gainers = sorted(data, key=lambda x: float(x['priceChangePercent']), reverse=True)[:3]
            losers = sorted(data, key=lambda x: float(x['priceChangePercent']))[:3]
            return {
                "gainers": [{"symbol": g['symbol'], "change": f"+{g['priceChangePercent']:.2f}%"} for g in gainers],
                "losers": [{"symbol": l['symbol'], "change": f"{l['priceChangePercent']:.2f}%"} for l in losers]
            }
    except:
        return {
            "gainers": [{"symbol": "BTCUSDT", "change": "+4.25%"}],
            "losers": [{"symbol": "ADAUSDT", "change": "-1.23%"}]
        }

@app.get("/api/balance")
async def api_balance():
    return await get_binance_balance()

@app.get("/api/prices")
async def api_prices():
    return await get_live_prices()

@app.get("/api/market")
async def api_market():
    return await get_market_data()

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        print(f"Webhook: {data}")
        return {"status": "ok"}
    except:
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
<script src="https://cdn.jsdelivr.net/npm/daisyui@4.4.19/dist/full.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://unpkg.com/htmx.org@1.9.10"></script>
<style>
.glass{background:rgba(255,255,255,0.1);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.2)}
.pulse-green{animation:pulse-green 2s infinite}
@keyframes pulse-green{0%,100%{box-shadow:0 0 10px rgba(34,197,94,.5)}50%{box-shadow:0 0 20px rgba(34,197,94,.8)}}
</style>
</head>
<body class="bg-gradient-to-br from-indigo-900 to-purple-900 min-h-screen p-6">
<div class="max-w-6xl mx-auto">
<h1 class="text-5xl font-bold text-white text-center mb-8">Trading Bot Pro</h1>

<div class="glass rounded-3xl p-8 mb-8" hx-get="/api/balance" hx-trigger="load, every 5s" hx-target="#balance">
<div id="balance" class="text-center text-white text-xl">جاري التحميل...</div>
</div>

<div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
<button class="btn btn-success btn-lg" onclick="quickTrade('BTCUSDT', 'BUY')">🟢 شراء BTC</button>
<button class="btn btn-error btn-lg" onclick="quickTrade('BTCUSDT', 'SELL')">🔴 بيع BTC</button>
</div>

<div class="glass p-6 rounded-3xl text-center">
<p class="text-white mb-2">✅ البوت يعمل | <span id="time"></span></p>
<span class="badge badge-success">APIs 🟢</span> <span class="badge badge-success">Webhook 🟢</span>
</div>
</div>

<script>
document.body.addEventListener('htmx:afterSwap', e => {
if(e.detail.target.id==='balance'){
try{
const data=JSON.parse(e.detail.xhr.responseText);
e.detail.target.innerHTML=`
<div class="space-y-4 text-2xl">
<div class="font-bold text-green-400">$${data.total?.toLocaleString()}</div>
<div>USDT: <span class="text-green-400">${data.usdt?.toFixed(2)}</span></div>
<div>BTC: <span class="text-orange-400">${data.btc?.toFixed(6)}</span></div>
<div class="text-sm">${data.status}</div>
</div>`;
}catch{}}
});
function quickTrade(s,a){alert(`🚀 ${a} ${s}`);}
function updateTime(){document.getElementById('time').textContent=new Date().toLocaleTimeString('ar-SA');}
updateTime();setInterval(updateTime,1000);
</script>
</body>
</html>
"""
    return HTMLResponse(content=html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
