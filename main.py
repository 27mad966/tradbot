import os, asyncio, ccxt, uvicorn
from datetime import datetime
from collections import deque
from fastapi import FastAPI, WebSocket, Form
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
                if amt > 0:
                    try: total += amt * self.ex.fetch_ticker(f"{c}/USDT")['last']
                    except: continue
            if 9950 < total < 10050 and not self.trades: total = INITIAL_BALANCE
            pnl = total - INITIAL_BALANCE
            return round(total, 2), round(pnl, 2), round((pnl/INITIAL_BALANCE)*100, 2)
        except: return 10000.0, 0.0, 0.0

    def execute(self, pair, side):
        if not settings["active"]: return
        pair = pair.upper().replace("USDTUSDT", "USDT")
        if "/" not in pair: pair = f"{pair[:-4]}/USDT" if pair.endswith("USDT") else f"{pair}/USDT"
        try:
            self.ex.load_markets()
            price = self.ex.fetch_ticker(pair)['last']
            if side == "buy":
                val = settings["buy_value"] if settings["buy_mode"] == "fixed" else self.ex.fetch_balance()['total'].get('USDT', 0) * settings["buy_value"]
                if val < 11: val = 11
                amt = self.ex.amount_to_precision(pair, val / price)
                self.ex.create_market_buy_order(pair, amt)
            else:
                amt = self.ex.amount_to_precision(pair, self.ex.fetch_balance()['total'].get(pair.split('/')[0], 0) * settings["sell_value"])
                self.ex.create_market_sell_order(pair, amt)
            res = {'time': datetime.now().strftime("%H:%M"), 'pair': pair, 'act': side, 'price': price, 'st': "✅ بنجاح"}
            self.trades.appendleft(res)
            return res
        except Exception as e:
            res = {'time': datetime.now().strftime("%H:%M"), 'pair': pair, 'act': side, 'price': 0, 'st': f"❌ {str(e)[:15]}"}
            self.trades.appendleft(res)
            return res

bot = TradingBot()

@app.get("/", response_class=HTMLResponse)
async def root():
    return f"""
    <body style="background:#0b0e11;color:white;font-family:sans-serif;padding:20px;text-align:right;" dir="rtl">
        <div style="display:flex;justify-content:space-between;background:#1e2329;padding:15px;border-radius:15px;margin-bottom:20px;">
            <h2 style="color:#f0b90b;margin:0;">SOVEREIGN V4.6</h2>
            <div>
                <button onclick="fetch('/liq',{{method:'POST'}})" style="background:#f6465d;color:white;border:none;padding:8px 15px;border-radius:10px;cursor:pointer;">تصفية 🚨</button>
            </div>
        </div>
        <div style="grid-template-columns:repeat(3,1fr);display:grid;gap:15px;margin-bottom:20px;">
            <div style="background:#1e2329;padding:15px;border-radius:15px;">رصيد: <span id="b">10000</span></div>
            <div style="background:#1e2329;padding:15px;border-radius:15px;">ربح: <span id="p">0</span></div>
            <div style="background:#1e2329;padding:15px;border-radius:15px;">نسبة: <span id="n">0%</span></div>
        </div>
        <div style="background:#1e2329;padding:20px;border-radius:20px;">
            <table style="width:100%;text-align:right;font-size:12px;">
                <thead><tr style="color:#848e9c;"><th>الوقت</th><th>الزوج</th><th>العملية</th><th>السعر</th><th>الحالة</th></tr></thead>
                <tbody id="t"></tbody>
            </table>
        </div>
        <script>
            const ws = new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws');
            ws.onmessage = (e) => {{
                const d = JSON.parse(e.data);
                document.getElementById('b').innerText = d.t;
                document.getElementById('p').innerText = d.p;
                document.getElementById('n').innerText = d.n + '%';
                document.getElementById('t').innerHTML = d.tr.map(x => `<tr><td>${{x.time}}</td><td>${{x.pair}}</td><td style="color:${{x.act==='buy'?'#2ebd85':'#f6465d'}}">${{x.act}}</td><td>${{x.price}}</td><td>${{x.st}}</td></tr>`).join('');
            }};
        </script>
    </body>
    """

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    while True:
        t, p, n = await bot.get_stats()
        await ws.send_json({{"t": t, "p": p, "n": n, "tr": list(bot.trades)}})
        await asyncio.sleep(4)

@app.post("/update_settings")
async def upd(k: str = Form(...), v: str = Form(...)):
    settings[k] = float(v) if k.endswith('value') else v
    return {{"ok": True}}

@app.post("/liq")
async def liq(): bot.ex.fetch_balance(); return {{"ok": True}}

@app.post("/webhook")
async def wh(s: BaseModel): return bot.execute(s.pair, s.direction)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
