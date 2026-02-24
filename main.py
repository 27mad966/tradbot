from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import httpx
import time
from datetime import datetime

app = FastAPI()

API_KEY = "test"
SECRET_KEY = "test"

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
        action = data


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html = """
<!DOCTYPE html>
<html><head><script src="https://cdn.tailwindcss.com"></script><script src="https://unpkg.com/htmx.org@1.9.10"></script></head>
<body class="bg-gradient-to-br from-indigo-900 to-purple-900 min-h-screen p-6 text-white">
<div class="max-w-4xl mx-auto">
<h1 class="text-4xl font-bold text-center mb-8">🚀 Trading Bot Pro</h1>
<div class="bg-white/10 backdrop-blur p-8 rounded-3xl mb-8" hx-get="/api/balance" hx-trigger="load, every 5s" hx-target="#balance">
<div id="balance">جاري التحميل...</div>
</div>
<div class="grid grid-cols-2 gap-4 mb-8">
<button class="bg-green-500 hover:bg-green-600 p-4 rounded-xl" onclick="alert('🟢 Buy')">شراء</button>
<button class="bg-red-500 hover:bg-red-600 p-4 rounded-xl" onclick="alert('🔴 Sell')">بيع</button>
</div>
<p class="text-center">Webhook: https://tradbot-2qlz.onrender.com/webhook ✅</p>
</div>
<script>
document.body.addEventListener('htmx:afterSwap',e=>{if(e.detail.target.id==='balance'){try{const d=JSON.parse(e.detail.xhr.responseText);e.detail.target.innerHTML=`<div>$${d.total?.toLocaleString()}</div><div>USDT: ${d.usdt?.toFixed(2)}</div>`;}catch{}}});
</script>
</body></html>
"""
    return HTMLResponse(html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

