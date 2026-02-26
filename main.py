import os, asyncio, ccxt, uvicorn
from datetime import datetime
from collections import deque
from fastapi import FastAPI, WebSocket, Form
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Signal(BaseModel):
    pair: str
    direction: str

INITIAL_BALANCE = 10000.0  
# تأكد من أن "active" هي True دائماً عند التشغيل
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
                    ticker = self.ex.fetch_ticker(f"{c}/USDT")
                    total += amt * ticker['last']
            pnl = total - INITIAL_BALANCE
            return round(total, 2), round(pnl, 2), round((pnl/INITIAL_BALANCE)*100, 2)
        except: return 10000.0, 0.0, 0.0

    def execute(self, pair, side):
        # تحويل الإشارة لنص صغير لتجنب أخطاء الحروف
        side = side.lower() 
        pair = pair.upper().replace("USDTUSDT", "USDT")
        if "/" not in pair: pair = f"{pair[:-4]}/USDT" if pair.endswith("USDT") else f"{pair}/USDT"
        
        print(f"🚀 استلام إشارة: {side} لزوج {pair}") # سيظهر في سجل ريندر
        
        try:
            self.ex.load_markets()
            price = self.ex.fetch_ticker(pair)['last']
            
            if "buy" in side or "long" in side:
                bal = self.ex.fetch_balance()
                usdt = bal['total'].get('USDT', 0)
                val = settings["buy_value"] if settings["buy_mode"] == "fixed" else usdt * settings["buy_value"]
                if val < 11: val = 11
                amt = self.ex.amount_to_precision(pair, val / price)
                order = self.ex.create_market_buy_order(pair, amt)
                msg = f"✅ شراء {amt}"
            else:
                coin = pair.split('/')[0]
                bal = self.ex.fetch_balance()
                c_bal = bal['total'].get(coin, 0)
                amt = self.ex.amount_to_precision(pair, c_bal * settings["sell_value"])
                order = self.ex.create_market_sell_order(pair, amt)
                msg = f"✅ بيع {amt}"

            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'act': side, 'price': price, 'st': msg}
            self.trades.appendleft(res)
            print(f"💰 نجاح العملية: {msg}")
            return res
        except Exception as e:
            err = str(e)
            print(f"❌ فشل التنفيذ: {err}")
            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'act': side, 'price': 0, 'st': f"❌ {err[:20]}"}
            self.trades.appendleft(res)
            return res

bot = TradingBot()

@app.get("/", response_class=HTMLResponse)
async def root():
    # الواجهة المحسنة التي تضمن التحديث الفوري
    return f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head><meta charset="UTF-8"><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-[#0b0e11] text-white p-6 font-sans">
        <div class="max-w-4xl mx-auto">
            <div class="flex justify-between bg-white/5 p-6 rounded-2xl mb-6">
                <h1 class="text-yellow-500 font-black italic">SOVEREIGN V4.8</h1>
                <div class="text-xs text-emerald-400 font-bold">رصيد: <span id="b">10000</span></div>
            </div>
            <div class="bg-white/5 rounded-2xl overflow-hidden">
                <table class="w-full text-right text-sm">
                    <thead class="bg-white/10 text-gray-400"><tr><th class="p-4">الوقت</th><th class="p-4">الزوج</th><th class="p-4">النوع</th><th class="p-4">السعر</th><th class="p-4">الحالة</th></tr></thead>
                    <tbody id="t" class="divide-y divide-gray-800"></tbody>
                </table>
            </div>
        </div>
        <script>
            const ws = new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws');
            ws.onmessage = (e) => {{
                const d = JSON.parse(e.data);
                document.getElementById('b').innerText = d.t.toLocaleString();
                document.getElementById('t').innerHTML = d.tr.map(x => `<tr><td class="p-4 text-gray-500">${{x.time}}</td><td class="p-4 font-bold">${{x.pair}}</td><td class="p-4 uppercase ${{x.act.includes('buy')?'text-emerald-400':'text-red-400'}}">${{x.act}}</td><td class="p-4 text-yellow-500">${{x.price}}</td><td class="p-4 text-xs font-bold text-gray-300">${{x.st}}</td></tr>`).join('');
            }};
        </script>
    </body></html>
    """

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    while True:
        try:
            t, p, n = await bot.get_stats()
            await ws.send_json({{"t": t, "tr": list(bot.trades)}})
        except: pass
        await asyncio.sleep(4)

@app.post("/webhook")
async def wh(s: Signal): 
    # تنفيذ العملية بشكل مباشر وصريح
    return bot.execute(s.pair, s.direction)

@app.post("/liq")
async def liq(): bot.liquidate_all(); return {{"ok": True}}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
