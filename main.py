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

app = FastAPI(title="Sovereign Station Ultimate")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- الإعدادات ---
INITIAL_BALANCE = 10000.0  
settings = {
    "buy_mode": "fixed", 
    "buy_value": 100.0,
    "sell_mode": "percent",
    "sell_value": 1.0,
    "bot_active": True
}

class TradingBot:
    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY", "").strip()
        self.secret_key = os.getenv("BINANCE_SECRET_KEY", "").strip()
        self.exchange = ccxt.binance({
            'apiKey': self.api_key, 'secret': self.secret_key,
            'enableRateLimit': True,
            'options': {'adjustForTimeDifference': True, 'recvWindow': 15000, 'defaultType': 'spot'}
        })
        self.exchange.set_sandbox_mode(True)
        self.trades = deque(maxlen=50)

    async def get_stats(self):
        try:
            bal = self.exchange.fetch_balance()
            total_usdt = bal['total'].get('USDT', 0.0)
            active_assets_value = 0
            # تصفية العملات الوهمية وحساب العملات الرئيسية فقط لضمان دقة الربح
            for coin in ['BTC', 'ETH', 'SOL', 'BNB', 'ADA', 'XRP', 'DOT']:
                amount = bal['total'].get(coin, 0.0)
                if amount > 0:
                    try:
                        ticker = self.exchange.fetch_ticker(f"{coin}/USDT")
                        active_assets_value += amount * ticker['last']
                    except: continue
            
            current_total = total_usdt + active_assets_value
            if current_total < 10.0: current_total = INITIAL_BALANCE
            
            pnl_val = current_total - INITIAL_BALANCE
            pnl_pct = (pnl_val / INITIAL_BALANCE) * 100
            return round(current_total, 2), round(pnl_val, 2), round(pnl_pct, 2)
        except: return INITIAL_BALANCE, 0.0, 0.0

    def execute_trade(self, pair, direction):
        if not settings["bot_active"]: return
        pair = pair.replace("USDTUSDT", "USDT").upper()
        if "/" not in pair: pair = f"{pair[:-4]}/USDT" if pair.endswith("USDT") else f"{pair}/USDT"
        
        try:
            ticker = self.exchange.fetch_ticker(pair)
            price = ticker['last']
            bal = self.exchange.fetch_balance()
            
            if direction.lower() in ["buy", "long"]:
                usdt_bal = bal['total'].get('USDT', 0)
                val = settings["buy_value"] if settings["buy_mode"] == "fixed" else usdt_bal * settings["buy_value"]
                if val > usdt_bal: val = usdt_bal * 0.98
                amount = val / price
                self.exchange.create_market_buy_order(pair, amount)
                act = "شراء"
            else:
                coin = pair.split('/')[0]
                coin_bal = bal['total'].get(coin, 0)
                amount = coin_bal * settings["sell_value"] if settings["sell_mode"] == "percent" else settings["sell_value"] / price
                if amount > coin_bal: amount = coin_bal
                self.exchange.create_market_sell_order(pair, amount)
                act = "بيع"

            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': act, 'price': round(price, 4), 'status': f"✅ تنفيذ {round(amount, 2)}"}
            self.trades.appendleft(res)
            return res
        except Exception as e:
            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': "خطأ", 'price': 0, 'status': f"❌ {str(e)[:15]}"}
            self.trades.appendleft(res)
            return res

    def liquidate_all(self):
        try:
            bal = self.exchange.fetch_balance()
            for coin, amount in bal['total'].items():
                if amount > 0.001 and coin not in ['USDT', 'BNB']:
                    try: self.exchange.create_market_sell_order(f"{coin}/USDT", amount)
                    except: continue
            return True
        except: return False

bot = TradingBot()

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8"><title>Sovereign Elite Station</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap'); body {{ font-family: 'Cairo', sans-serif; background: #0b0e11; color: white; }}</style>
    </head>
    <body class="p-4 md:p-10">
        <div class="max-w-6xl mx-auto">
            <div class="flex justify-between items-center mb-10">
                <h1 class="text-3xl font-black text-yellow-500 italic uppercase">Sovereign V4.5</h1>
                <div class="flex gap-3">
                    <button id="p-btn" onclick="toggleBot()" class="px-6 py-2 rounded-2xl font-bold bg-yellow-600 hover:bg-yellow-500 transition-all">إيقاف ⏸</button>
                    <button onclick="panic()" class="px-6 py-2 rounded-2xl font-bold bg-red-600 hover:bg-red-500 transition-all">تصفية المحفظة 🚨</button>
                </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8 text-right">
                <div class="bg-white/5 p-6 rounded-[2rem] border border-white/10"><p class="text-gray-500 text-[10px] uppercase mb-1">إجمالي المحفظة</p><div id="total_bal" class="text-2xl font-black font-mono text-white">10,000.00</div></div>
                <div class="bg-white/5 p-6 rounded-[2rem] border border-white/10"><p class="text-gray-500 text-[10px] uppercase mb-1">صافي الربح ($)</p><div id="pnl_val" class="text-2xl font-black font-mono">0.00</div></div>
                <div class="bg-white/5 p-6 rounded-[2rem] border border-white/10"><p class="text-gray-500 text-[10px] uppercase mb-1">النسبة المئوية</p><div id="pnl_pct" class="text-2xl font-black font-mono">0%</div></div>
                <div class="bg-white/5 p-6 rounded-[2rem] border border-white/10 text-center"><div id="tag" class="text-[10px] text-emerald-500 font-bold mb-1 uppercase">Bot Active</div><div class="h-1.5 w-full bg-gray-800 rounded-full overflow-hidden"><div id="progress" class="h-full bg-emerald-500 w-full animate-pulse"></div></div></div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-10 text-right">
                <div class="bg-white/5 p-8 rounded-[2rem] border border-emerald-500/20">
                    <h3 class="text-emerald-400 font-bold mb-4 text-sm">🟢 إعدادات الشراء</h3>
                    <select onchange="upd('buy_mode',this.value)" class="bg-gray-800 w-full p-3 rounded-xl mb-3 text-xs border-none outline-none"><option value="fixed">مبلغ ثابت ($)</option><option value="percent">نسبة المحفظة</option></select>
                    <input type="number" value="100" onchange="upd('buy_value',this.value)" class="bg-gray-800 w-full p-3 rounded-xl text-lg font-bold border-none outline-none">
                </div>
                <div class="bg-white/5 p-8 rounded-[2rem] border border-red-500/20">
                    <h3 class="text-red-400 font-bold mb-4 text-sm">🔴 إعدادات البيع</h3>
                    <select onchange="upd('sell_mode',this.value)" class="bg-gray-800 w-full p-3 rounded-xl mb-3 text-xs border-none outline-none"><option value="percent">نسبة العملة</option><option value="fixed">مبلغ ثابت ($)</option></select>
                    <input type="number" value="1.0" step="0.1" onchange="upd('sell_value',this.value)" class="bg-gray-800 w-full p-3 rounded-xl text-lg font-bold border-none outline-none">
                </div>
            </div>
            <div class="bg-white/5 rounded-[2.5rem] overflow-hidden border border-white/10 text-right">
                <table class="w-full text-sm"><thead class="bg-white/5 text-gray-500 text-[10px]"><tr><th class="p-5 uppercase">الوقت</th><th class="p-5 uppercase">الزوج</th><th class="p-5 uppercase">العملية</th><th class="p-5 uppercase">السعر</th><th class="p-5 uppercase">الحالة</th></tr></thead>
                <tbody id="table" class="divide-y divide-gray-800"><tr><td colspan="5" class="p-10 text-center text-gray-600 font-bold">بانتظار إشارة تريدينق فيو...</td></tr></tbody></table>
            </div>
        </div>
        <script>
            let active = true;
            async function upd(k,v) {{ await fetch('/update_settings',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:`key=${{k}}&value=${{v}}` }}); }}
            async function toggleBot() {{ 
                active = !active; document.getElementById('p-btn').textContent = active?'إيقاف ⏸':'تشغيل ▶️';
                document.getElementById('p-btn').className = active?'px-6 py-2 rounded-2xl font-bold bg-yellow-600 text-sm':'px-6 py-2 rounded-2xl font-bold bg-emerald-600 text-sm';
                document.getElementById('tag').textContent = active?'BOT ACTIVE':'BOT PAUSED';
                document.getElementById('tag').className = active?'text-[10px] text-emerald-500 font-bold mb-1':'text-[10px] text-red-500 font-bold mb-1';
                document.getElementById('progress').className = active?'h-full bg-emerald-500 w-full animate-pulse':'h-full bg-red-500 w-full';
                await upd('bot_active',active); 
            }}
            async function panic() {{ if(confirm('⚠️ هل أنت متأكد من تصفية كافة المراكز وبيعها مقابل USDT؟')) await fetch('/liquidate',{{method:'POST'}}); }}
            const ws = new WebSocket(`${{window.location.protocol==='https:'?'wss:':'ws:'}}//${{window.location.host}}/ws`);
            ws.onmessage = (e) => {{
                const d = JSON.parse(e.data);
                document.getElementById('total_bal').textContent = d.total.toLocaleString();
                document.getElementById('pnl_val').textContent = (d.pnl >= 0 ? '+' : '') + d.pnl;
                document.getElementById('pnl_val').style.color = d.pnl >= 0 ? '#10b981' : '#ef4444';
                document.getElementById('pnl_pct').textContent = d.pnl_pct + '%';
                if(d.trades.length > 0) {{
                    document.getElementById('table').innerHTML = d.trades.map(t => `<tr class="border-b border-gray-800 hover:bg-white/5 transition-all"><td class="p-5 text-xs text-gray-500 font-mono">${{t.time}}</td><td class="p-5 font-bold text-white text-xs">${{t.pair}}</td><td class="p-5 font-bold text-xs ${{t.action==='buy' || t.action==='شراء'?'text-emerald-400':'text-red-400'}} uppercase">${{t.action}}</td><td class="p-5 text-yellow-500 font-mono font-bold text-xs">${{t.price}}</td><td class="p-5 text-[10px] font-bold text-gray-300 tracking-tight">${{t.status}}</td></tr>`).join('');
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
    return {"status": "ok"}

@app.post("/liquidate")
async def liquidate():
    bot.liquidate_all()
    return {"status": "ok"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            total, pnl, pnl_p = await bot.get_stats()
            await websocket.send_json({"total": total, "pnl": pnl, "pnl_pct": pnl_p, "trades": list(bot.trades)})
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
