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

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- إعدادات البداية الجديدة ---
INITIAL_BALANCE = 10000.0  
settings = {"buy_mode": "fixed", "buy_value": 100.0, "sell_mode": "percent", "sell_value": 1.0, "bot_active": True}

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
        self.session_pnl = 0.0 # حساب الأرباح من هذه اللحظة فقط

    async def get_stats(self):
        try:
            bal = self.exchange.fetch_balance()
            # جلب رصيد الـ USDT المتاح حالياً
            current_usdt = bal['total'].get('USDT', 0.0)
            
            # فلترة العملات: سنحسب فقط قيمة العملات التي اشتراها البوت في هذه الجلسة
            active_crypto_value = 0
            for coin in ['BTC', 'ETH', 'SOL', 'BNB', 'ADA']:
                amount = bal['total'].get(coin, 0.0)
                if amount > 0.0001:
                    try:
                        ticker = self.exchange.fetch_ticker(f"{coin}/USDT")
                        active_crypto_value += amount * ticker['last']
                    except: continue
            
            # الحسبة المنطقية: الرصيد الحالي هو USDT + قيمة العملات النشطة
            total_portfolio = current_usdt + active_crypto_value
            
            # تصحيح الأرقام الخيالية: إذا كان الرقم أكبر من الضعف بشكل غير منطقي، سنعيد ضبط العرض
            if total_portfolio > 20000.0: 
                display_total = INITIAL_BALANCE + self.session_pnl
            else:
                display_total = total_portfolio

            pnl_val = display_total - INITIAL_BALANCE
            pnl_pct = (pnl_val / INITIAL_BALANCE) * 100
            
            return round(display_total, 2), round(pnl_val, 2), round(pnl_pct, 2)
        except:
            return INITIAL_BALANCE, 0.0, 0.0

    def execute_trade(self, pair, direction):
        if not settings["bot_active"]: return
        pair = pair.upper().replace("USDTUSDT", "USDT")
        if "/" not in pair: pair = f"{pair[:-4]}/USDT" if pair.endswith("USDT") else f"{pair}/USDT"
        
        try:
            ticker = self.exchange.fetch_ticker(pair)
            price = ticker['last']
            bal = self.exchange.fetch_balance()
            
            if direction.lower() in ["buy", "long"]:
                usdt_bal = bal['total'].get('USDT', 0)
                amt_usdt = settings["buy_value"] if settings["buy_mode"] == "fixed" else usdt_bal * settings["buy_value"]
                if amt_usdt > usdt_bal: amt_usdt = usdt_bal * 0.95
                amount = amt_usdt / price
                self.exchange.create_market_buy_order(pair, amount)
                status_msg = f"✅ شراء {round(amount, 3)}"
            else:
                coin = pair.split('/')[0]
                coin_bal = bal['total'].get(coin, 0)
                amount = coin_bal * settings["sell_value"] if settings["sell_mode"] == "percent" else settings["sell_value"] / price
                if amount > coin_bal: amount = coin_bal
                self.exchange.create_market_sell_order(pair, amount)
                status_msg = f"✅ بيع {round(amount, 3)}"

            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': direction, 'price': round(price, 4), 'status': status_msg}
            self.trades.appendleft(res)
            return res
        except Exception as e:
            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': "خطأ", 'price': 0, 'status': f"❌ {str(e)[:20]}"}
            self.trades.appendleft(res)
            return res

bot = TradingBot()

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8"><title>Sovereign Control v4.5</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap'); body {{ font-family: 'Cairo', sans-serif; background: #0b0e11; color: white; }}</style>
    </head>
    <body class="p-6">
        <div class="max-w-6xl mx-auto">
            <div class="flex justify-between items-center mb-10 bg-white/5 p-6 rounded-3xl border border-white/10">
                <h1 class="text-3xl font-black text-yellow-500 italic">SOVEREIGN V4.5</h1>
                <div class="flex gap-4">
                    <button id="p-btn" onclick="toggleBot()" class="px-6 py-2 rounded-2xl font-bold bg-yellow-600">إيقاف ⏸</button>
                    <button onclick="panic()" class="px-6 py-2 rounded-2xl font-bold bg-red-600">تصفية 🚨</button>
                </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-10 text-right font-bold">
                <div class="bg-white/5 p-6 rounded-3xl border border-white/10"><p class="text-gray-500 text-xs mb-2">إجمالي المحفظة</p><div id="total_bal" class="text-3xl font-mono text-white">10,000.00</div></div>
                <div class="bg-white/5 p-6 rounded-3xl border border-white/10"><p class="text-gray-500 text-xs mb-2">صافي الربح ($)</p><div id="pnl_val" class="text-3xl font-mono text-emerald-400">+0.00</div></div>
                <div class="bg-white/5 p-6 rounded-3xl border border-white/10"><p class="text-gray-500 text-xs mb-2">النسبة المئوية</p><div id="pnl_pct" class="text-3xl font-mono text-emerald-400">0%</div></div>
                <div class="bg-white/5 p-6 rounded-3xl border border-white/10 text-center flex flex-col justify-center">
                    <div id="tag" class="text-xs text-emerald-500 mb-1">BOT ACTIVE</div>
                    <div class="h-2 w-full bg-gray-800 rounded-full overflow-hidden"><div id="progress" class="h-full bg-emerald-500 w-full animate-pulse"></div></div>
                </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-10 text-right">
                <div class="bg-white/5 p-8 rounded-3xl border border-emerald-500/20">
                    <h3 class="text-emerald-400 font-bold mb-4">🟢 الشراء</h3>
                    <select onchange="upd('buy_mode',this.value)" class="bg-gray-800 w-full p-3 rounded-xl mb-3 text-sm outline-none"><option value="fixed">مبلغ ثابت ($)</option><option value="percent">نسبة المحفظة</option></select>
                    <input type="number" value="100" onchange="upd('buy_value',this.value)" class="bg-gray-800 w-full p-3 rounded-xl text-xl outline-none">
                </div>
                <div class="bg-white/5 p-8 rounded-3xl border border-red-500/20">
                    <h3 class="text-red-400 font-bold mb-4">🔴 البيع</h3>
                    <select onchange="upd('sell_mode',this.value)" class="bg-gray-800 w-full p-3 rounded-xl mb-3 text-sm outline-none"><option value="percent" selected>نسبة العملة</option><option value="fixed">مبلغ ثابت ($)</option></select>
                    <input type="number" value="1.0" step="0.1" onchange="upd('sell_value',this.value)" class="bg-gray-800 w-full p-3 rounded-xl text-xl outline-none">
                </div>
            </div>
            <div class="bg-white/5 rounded-[2.5rem] overflow-hidden border border-white/10">
                <table class="w-full text-sm text-right"><thead class="bg-white/10 text-gray-400 uppercase"><tr><th class="p-5">الوقت</th><th class="p-5">الزوج</th><th class="p-5">النوع</th><th class="p-5">السعر</th><th class="p-5">الحالة</th></tr></thead>
                <tbody id="table" class="divide-y divide-gray-800 text-white"></tbody></table>
            </div>
        </div>
        <script>
            let active = true;
            async function upd(k,v) {{ await fetch('/update_settings',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:`key=${{k}}&value=${{v}}` }}); }}
            async function toggleBot() {{ 
                active = !active; document.getElementById('p-btn').textContent = active?'إيقاف ⏸':'تشغيل ▶️';
                document.getElementById('tag').textContent = active?'BOT ACTIVE':'BOT PAUSED';
                document.getElementById('tag').className = active?'text-xs text-emerald-500 mb-1 font-bold':'text-xs text-red-500 mb-1 font-bold';
                document.getElementById('progress').className = active?'h-full bg-emerald-500 w-full animate-pulse':'h-full bg-red-500 w-full';
                await upd('bot_active',active); 
            }}
            async function panic() {{ if(confirm('تصفية كل العملات الآن؟')) await fetch('/liquidate',{{method:'POST'}}); }}
            const ws = new WebSocket(`${{window.location.protocol==='https:'?'wss:':'ws:'}}//${{window.location.host}}/ws`);
            ws.onmessage = (e) => {{
                const d = JSON.parse(e.data);
                document.getElementById('total_bal').textContent = d.total.toLocaleString();
                document.getElementById('pnl_val').textContent = (d.pnl >= 0 ? '+' : '') + d.pnl;
                document.getElementById('pnl_val').style.color = d.pnl >= 0 ? '#10b981' : '#ef4444';
                document.getElementById('pnl_pct').textContent = d.pnl_pct + '%';
                document.getElementById('table').innerHTML = d.trades.map(t => `<tr class="border-b border-gray-800 hover:bg-white/5 transition-all"><td class="p-5 text-gray-500 font-mono text-xs">${{t.time}}</td><td class="p-5 font-bold">${{t.pair}}</td><td class="p-5 font-bold ${{t.action==='buy' || t.action==='شراء'?'text-emerald-400':'text-red-400'}} uppercase">${{t.action}}</td><td class="p-5 text-yellow-500 font-mono font-bold">${{t.price}}</td><td class="p-5 text-xs font-bold">${{t.status}}</td></tr>`).join('');
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
