import os, asyncio, ccxt, uvicorn
from datetime import datetime
from collections import deque
from fastapi import FastAPI, WebSocket, Form
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- قالب البيانات الخاص بالإشارة ---
class Signal(BaseModel):
    pair: str
    direction: str

INITIAL_BALANCE = 10000.0  
settings = {"buy_mode": "fixed", "buy_value": 100.0, "sell_mode": "percent", "sell_value": 1.0, "active": True}

class TradingBot:
    def __init__(self):
        self.ex = ccxt.binance({
            'apiKey': os.getenv("BINANCE_API_KEY", "").strip(),
            'secret': os.getenv("BINANCE_SECRET_KEY", "").strip(),
            'enableRateLimit': True,
            'options': {'adjustForTimeDifference': True, 'recvWindow': 15000, 'defaultType': 'spot'}
        })
        self.ex.set_sandbox_mode(True)
        self.trades = deque(maxlen=50)

    async def get_stats(self):
        try:
            bal = self.ex.fetch_balance()
            total = bal['total'].get('USDT', 0.0)
            for c in ['BTC', 'ETH', 'SOL', 'BNB']:
                amt = bal['total'].get(c, 0.0)
                if amt > 0.0001:
                    try: 
                        ticker = self.ex.fetch_ticker(f"{c}/USDT")
                        total += amt * ticker['last']
                    except: continue
            if not self.trades and 9900 < total < 10100: total = INITIAL_BALANCE
            pnl = total - INITIAL_BALANCE
            return round(total, 2), round(pnl, 2), round((pnl/INITIAL_BALANCE)*100, 2)
        except: return INITIAL_BALANCE, 0.0, 0.0

    def execute(self, pair, side):
        if not settings["active"]: return {"st": "⚠️ متوقف"}
        pair = pair.upper().replace("USDTUSDT", "USDT")
        if "/" not in pair: pair = f"{pair[:-4]}/USDT" if pair.endswith("USDT") else f"{pair}/USDT"
        try:
            self.ex.load_markets()
            price = self.ex.fetch_ticker(pair)['last']
            if side.lower() in ["buy", "long"]:
                val = settings["buy_value"] if settings["buy_mode"] == "fixed" else self.ex.fetch_balance()['total'].get('USDT', 0) * settings["buy_value"]
                if val < 11: val = 11
                amt = self.ex.amount_to_precision(pair, val / price)
                self.ex.create_market_buy_order(pair, amt)
                msg = f"✅ شراء {amt}"
            else:
                coin = pair.split('/')[0]
                amt = self.ex.amount_to_precision(pair, self.ex.fetch_balance()['total'].get(coin, 0) * settings["sell_value"])
                self.ex.create_market_sell_order(pair, amt)
                msg = f"✅ بيع {amt}"
            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'act': side, 'price': price, 'st': msg}
            self.trades.appendleft(res)
            return res
        except Exception as e:
            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'act': side, 'price': 0, 'st': f"❌ {str(e)[:15]}"}
            self.trades.appendleft(res)
            return res

bot = TradingBot()

@app.get("/", response_class=HTMLResponse)
async def root():
    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8"><title>Sovereign Elite v4.7</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap'); body {{ font-family: 'Cairo', sans-serif; background: #0b0e11; color: white; }}</style>
    </head>
    <body class="p-6">
        <div class="max-w-6xl mx-auto">
            <div class="flex justify-between items-center mb-8 bg-white/5 p-5 rounded-2xl border border-white/10">
                <h1 class="text-2xl font-black text-yellow-500 italic">SOVEREIGN V4.7</h1>
                <button onclick="fetch('/liq',{{method:'POST'}})" class="bg-red-600 px-6 py-2 rounded-xl font-bold text-xs">تصفية 🚨</button>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8 text-right font-bold">
                <div class="bg-white/5 p-6 rounded-3xl border border-white/10">رصيد: <span id="b" class="text-xl font-mono">10000</span></div>
                <div class="bg-white/5 p-6 rounded-3xl border border-white/10">ربح: <span id="p" class="text-xl font-mono text-emerald-400">0</span></div>
                <div class="bg-white/5 p-6 rounded-3xl border border-white/10">نسبة: <span id="n" class="text-xl font-mono text-emerald-400">0%</span></div>
            </div>
            <div class="bg-white/5 rounded-3xl overflow-hidden border border-white/10">
                <table class="w-full text-sm text-right">
                    <thead class="bg-white/10"><tr><th class="p-4">الوقت</th><th class="p-4">الزوج</th><th class="p-4">العملية</th><th class="p-4">السعر</th><th class="p-4">الحالة</th></tr></thead>
                    <tbody id="t" class="divide-y divide-gray-800"></tbody>
                </table>
            </div>
        </div>
        <script>
            const ws = new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws');
            ws.onmessage = (e) => {{
                const d = JSON.parse(e.data);
                document.getElementById('b').innerText = d.t.toLocaleString();
                document.getElementById('p').innerText = (d.p >= 0 ? '+' : '') + d.p;
                document.getElementById('p').className = d.p >= 0 ? 'text-xl font-mono text-emerald-400' : 'text-xl font-mono text-red-400';
                document.getElementById('n').innerText = d.n + '%';
                document.getElementById('t').innerHTML = d.tr.map(x => `<tr><td class="p-4 text-xs text-gray-500">${{x.time}}</td><td class="p-4 font-bold">${{x.pair}}</td><td class="p-4 font-bold ${{x.act==='buy'?'text-emerald-400':'text-red-400'}} uppercase">${{x.act}}</td><td class="p-4 text-yellow-500">${{x.price}}</td><td class="p-4 text-xs">${{x.st}}</td></tr>`).join('');
            }};
        </script>
    </body>
    </html>
    """

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    while True:
        try:
            t, p, n = await bot.get_stats()
            await ws.send_json({{"t": t, "p": p, "n": n, "tr": list(bot.trades)}})
        except: pass
        await asyncio.sleep(4)

@app.post("/update_settings")
async def upd(k: str = Form(...), v: str = Form(...)):
    settings[k] = float(v) if k.endswith('value') else (v == "true")
    return {{"ok": True}}

@app.post("/liq")
async def liq(): 
    bot.liquidate_all()
    return {{"ok": True}}

@app.post("/webhook")
async def wh(s: Signal): 
    return bot.execute(s.pair, s.direction)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
