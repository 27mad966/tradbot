import os
import asyncio
import ccxt
from datetime import datetime
from collections import deque
from fastapi import FastAPI, WebSocket, Form
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Sovereign Control Center v4.2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- مخزن الإعدادات الحية (Global Settings) ---
settings = {
    "buy_mode": "fixed", 
    "buy_value": 100.0,
    "sell_mode": "percent",
    "sell_value": 1.0,
    "bot_active": True  # حالة البوت (يعمل/متوقف)
}

class TradingBot:
    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY", "").strip()
        self.secret_key = os.getenv("BINANCE_SECRET_KEY", "").strip()
        self.exchange = ccxt.binance({
            'apiKey': self.api_key, 'secret': self.secret_key,
            'enableRateLimit': True,
            'options': {'adjustForTimeDifference': True, 'recvWindow': 10000, 'defaultType': 'spot'}
        })
        self.exchange.set_sandbox_mode(True)
        self.trades = deque(maxlen=50)

    async def get_balance(self):
        try:
            bal = self.exchange.fetch_balance()
            return bal['total'].get('USDT', 0.0)
        except: return 0.0

    def calculate_amount(self, pair, direction, price):
        coin = pair.split('/')[0]
        bal = self.exchange.fetch_balance()
        if direction == "buy":
            if settings["buy_mode"] == "fixed": return settings["buy_value"] / price
            else: return (bal['total'].get('USDT', 0) * settings["buy_value"]) / price
        else:
            coin_bal = bal['total'].get(coin, 0)
            if settings["sell_mode"] == "fixed": return settings["sell_value"] / price
            else: return coin_bal * settings["sell_value"]

    def execute_trade(self, pair, direction):
        if not settings["bot_active"]:
            log = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': 'تجاهل', 'price': 0, 'status': '⚠️ التداول متوقف حالياً'}
            self.trades.appendleft(log)
            return log

        pair = pair.replace("USDTUSDT", "USDT").upper()
        if "/" not in pair: pair = f"{pair[:-4]}/USDT" if pair.endswith("USDT") else f"{pair}/USDT"
        
        try:
            ticker = self.exchange.fetch_ticker(pair)
            price = ticker['last']
            amount = self.calculate_amount(pair, direction, price)
            if amount <= 0: raise Exception("رصيد غير كافٍ")

            if direction.lower() in ["buy", "long"]: self.exchange.create_market_buy_order(pair, amount)
            else: self.exchange.create_market_sell_order(pair, amount)

            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': direction, 'price': round(price, 4), 'status': f"✅ تم تنفيذ {round(amount, 4)}"}
            self.trades.appendleft(res)
            return res
        except Exception as e:
            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': "خطأ", 'price': 0, 'status': f"❌ {str(e)[:25]}"}
            self.trades.appendleft(res)
            return res

    def liquidate_all(self):
        try:
            bal = self.exchange.fetch_balance()
            for coin, amount in bal['total'].items():
                if amount > 0 and coin not in ['USDT', 'BNB']:
                    pair = f"{coin}/USDT"
                    self.exchange.create_market_sell_order(pair, amount)
            return True
        except: return False

bot = TradingBot()

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>Sovereign Ultimate Control</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap');
            body {{ font-family: 'Cairo', sans-serif; background: #0b0e11; color: white; }}
            .card {{ background: rgba(23, 27, 34, 0.95); border: 1px solid #30363d; border-radius: 1.5rem; }}
        </style>
    </head>
    <body class="p-6">
        <div class="max-w-6xl mx-auto">
            <div class="flex justify-between items-center mb-8">
                <h1 class="text-3xl font-black text-yellow-500 italic">SOVEREIGN STATION v4.2</h1>
                <div class="flex gap-4">
                    <button id="pause-btn" onclick="toggleBot()" class="px-6 py-2 rounded-full font-bold bg-yellow-600 hover:bg-yellow-500">إيقاف مؤقت ⏸</button>
                    <button onclick="panicSell()" class="px-6 py-2 rounded-full font-bold bg-red-600 hover:bg-red-500">تصفية المحفظة 🚨</button>
                </div>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8 text-right">
                <div class="card p-6 border-emerald-500/30">
                    <h3 class="text-emerald-400 font-bold mb-4">🟢 إعدادات الشراء</h3>
                    <select onchange="update('buy_mode', this.value)" class="bg-gray-800 text-white p-2 rounded mb-2 w-full text-xs">
                        <option value="fixed">مبلغ ثابت ($)</option>
                        <option value="percent">نسبة من المحفظة</option>
                    </select>
                    <input type="number" value="100" onchange="update('buy_value', this.value)" class="bg-gray-800 border border-gray-600 p-2 w-full rounded text-sm">
                </div>
                <div class="card p-6 border-red-500/30">
                    <h3 class="text-red-400 font-bold mb-4">🔴 إعدادات البيع</h3>
                    <select onchange="update('sell_mode', this.value)" class="bg-gray-800 text-white p-2 rounded mb-2 w-full text-xs">
                        <option value="percent">نسبة من العملة المملوكة</option>
                        <option value="fixed">مبلغ ثابت ($)</option>
                    </select>
                    <input type="number" value="1.0" step="0.1" onchange="update('sell_value', this.value)" class="bg-gray-800 border border-gray-600 p-2 w-full rounded text-sm">
                </div>
                <div class="card p-6 text-center flex flex-col justify-center bg-white/5">
                    <p class="text-gray-500 text-xs mb-1">الرصيد المتاح حالياً</p>
                    <div id="balance" class="text-3xl font-black text-white">0.0 USDT</div>
                    <div id="status-tag" class="text-[10px] text-emerald-500 mt-2 font-bold uppercase tracking-widest bg-emerald-500/10 py-1 rounded-full">BOT ACTIVE</div>
                </div>
            </div>

            <div class="card overflow-hidden text-right border-gray-800">
                <table class="w-full text-sm">
                    <thead class="bg-white/5 text-gray-400"><tr><th class="p-4 text-right">الوقت</th><th class="p-4 text-right">الزوج</th><th class="p-4 text-right">العملية</th><th class="p-4 text-right">السعر</th><th class="p-4 text-right">الحالة</th></tr></thead>
                    <tbody id="trades-table" class="divide-y divide-gray-800">
                        <tr><td colspan="5" class="p-10 text-center text-gray-600 font-bold">بانتظار الإشارة الأولى من TradingView...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <script>
            let botActive = true;
            async function update(key, val) {{ 
                await fetch('/update_settings', {{method:'POST', headers:{{'Content-Type':'application/x-www-form-urlencoded'}}, body:`key=${{key}}&value=${{val}}` }}); 
            }}
            
            async function toggleBot() {{
                botActive = !botActive;
                const btn = document.getElementById('pause-btn');
                const tag = document.getElementById('status-tag');
                btn.textContent = botActive ? 'إيقاف مؤقت ⏸' : 'تشغيل البوت ▶️';
                btn.className = botActive ? 'px-6 py-2 rounded-full font-bold bg-yellow-600' : 'px-6 py-2 rounded-full font-bold bg-emerald-600';
                tag.textContent = botActive ? 'BOT ACTIVE' : 'BOT PAUSED';
                tag.className = botActive ? 'text-[10px] text-emerald-500 mt-2 font-bold' : 'text-[10px] text-red-500 mt-2 font-bold';
                await update('bot_active', botActive);
            }}

            async function panicSell() {{
                if(confirm('🚨 هل أنت متأكد من تصفية كافة العملات وبيعها مقابل USDT فوراً؟')) {{
                    await fetch('/liquidate', {{method:'POST'}});
                }}
            }}

            const ws = new WebSocket(`${{window.location.protocol==='https:'?'wss:':'ws:'}}//${{window.location.host}}/ws`);
            ws.onmessage = (e) => {{
                const d = JSON.parse(e.data);
                document.getElementById('balance').textContent = d.balance.toLocaleString() + ' USDT';
                if(d.trades.length > 0) {{
                    document.getElementById('trades-table').innerHTML = d.trades.map(t => `
                        <tr class="hover:bg-white/5 border-b border-gray-800">
                            <td class="p-4 text-gray-500 font-mono text-xs">${{t.time}}</td>
                            <td class="p-4 font-bold text-white">${{t.pair}}</td>
                            <td class="p-4 font-bold ${{t.action==='buy' || t.action==='شراء'?'text-emerald-400':'text-red-400'}}">${{t.action}}</td>
                            <td class="p-4 font-mono text-yellow-500">${{t.price}}</td>
                            <td class="p-4 text-xs font-bold text-gray-300">${{t.status}}</td>
                        </tr>
                    `).join('');
                }}
            }};
        </script>
    </body>
    </html>
    """)

@app.post("/update_settings")
async def update_settings(key: str = Form(...), value: str = Form(...)):
    if key == "bot_active": settings[key] = (value == "true")
    elif key in ["buy_value", "sell_value"]: settings[key] = float(value)
    else: settings[key] = value
    return {"status": "success"}

@app.post("/liquidate")
async def liquidate():
    bot.liquidate_all()
    return {"status": "liquidated"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            bal = await bot.get_balance()
            await websocket.send_json({"balance": bal, "trades": list(bot.trades)})
            await asyncio.sleep(4)
    except: pass

class Signal(BaseModel):
    pair: str
    direction: str

@app.post("/webhook")
async def handle_webhook(signal: Signal):
    return bot.execute_trade(signal.pair, signal.direction)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
