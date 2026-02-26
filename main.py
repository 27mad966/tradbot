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

app = FastAPI(title="Sovereign Station Ultimate v4.4")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- الإعدادات المتقدمة ---
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
        
        # إعداد المحرك مع Sandbox Mode
        self.exchange = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.secret_key,
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
                'recvWindow': 15000,
                'defaultType': 'spot'
            }
        })
        self.exchange.set_sandbox_mode(True)
        self.trades = deque(maxlen=50)

    async def get_stats(self):
        try:
            # جلب الرصيد الخام
            bal = self.exchange.fetch_balance()
            total_usdt = bal['total'].get('USDT', 0.0)
            
            # حساب قيمة العملات الأخرى المفتوحة
            other_assets_value = 0
            for coin, amount in bal['total'].items():
                if amount > 0.0001 and coin not in ['USDT', 'BNB', 'BUSD', 'BCC']:
                    try:
                        ticker = self.exchange.fetch_ticker(f"{coin}/USDT")
                        other_assets_value += amount * ticker['last']
                    except: continue
            
            current_total = total_usdt + other_assets_value
            
            # تصحيح في حال كان الحساب جديداً تماماً ولم تظهر فيه الـ 10000 بعد
            if current_total == 0:
                current_total = INITIAL_BALANCE
                
            pnl_val = current_total - INITIAL_BALANCE
            pnl_pct = (pnl_val / INITIAL_BALANCE) * 100
            
            return round(current_total, 2), round(pnl_val, 2), round(pnl_pct, 2)
        except Exception as e:
            print(f"Stats Error: {e}")
            return INITIAL_BALANCE, 0.0, 0.0

    def calculate_amount(self, pair, direction, price):
        coin = pair.split('/')[0]
        bal = self.exchange.fetch_balance()
        if direction == "buy":
            if settings["buy_mode"] == "fixed":
                return settings["buy_value"] / price
            else:
                usdt_on_hand = bal['total'].get('USDT', 0)
                return (usdt_on_hand * settings["buy_value"]) / price
        else:
            coin_on_hand = bal['total'].get(coin, 0)
            if settings["sell_mode"] == "fixed":
                return settings["sell_value"] / price
            else:
                return coin_on_hand * settings["sell_value"]

    def execute_trade(self, pair, direction):
        if not settings["bot_active"]:
            log = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': 'تجاهل', 'price': 0, 'status': '⏸ متوقف'}
            self.trades.appendleft(log)
            return log

        # تصحيح الزوج لضمان التوافق مع API بايننس
        pair = pair.replace("USDTUSDT", "USDT").upper()
        if "/" not in pair:
            pair = f"{pair[:-4]}/USDT" if pair.endswith("USDT") else f"{pair}/USDT"
        
        try:
            ticker = self.exchange.fetch_ticker(pair)
            price = ticker['last']
            amount = self.calculate_amount(pair, direction, price)
            
            if amount <= 0:
                raise Exception("رصيد غير كافٍ")

            if direction.lower() in ["buy", "long"]:
                self.exchange.create_market_buy_order(pair, amount)
                act_name = "شراء"
            else:
                self.exchange.create_market_sell_order(pair, amount)
                act_name = "بيع"

            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': act_name, 'price': round(price, 4), 'status': f"✅ تم تنفيذ {round(amount, 2)}"}
            self.trades.appendleft(res)
            return res
        except Exception as e:
            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': "خطأ", 'price': 0, 'status': f"❌ {str(e)[:20]}"}
            self.trades.appendleft(res)
            return res

    def liquidate_all(self):
        try:
            bal = self.exchange.fetch_balance()
            for coin, amount in bal['total'].items():
                if amount > 0.001 and coin not in ['USDT', 'BNB', 'BUSD']:
                    try:
                        self.exchange.create_market_sell_order(f"{coin}/USDT", amount)
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
        <meta charset="UTF-8"><title>Sovereign Control Center</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap'); body {{ font-family: 'Cairo', sans-serif; background: #0b0e11; color: white; }}</style>
    </head>
    <body class="p-4 md:p-6 text-right">
        <div class="max-w-6xl mx-auto">
            <div class="flex justify-between items-center mb-8 bg-white/5 p-4 rounded-2xl border border-white/10">
                <h1 class="text-2xl font-black text-yellow-500 italic uppercase">Sovereign v4.4</h1>
                <div class="flex gap-2">
                    <button id="p-btn" onclick="toggleBot()" class="px-4 py-2 rounded-xl font-bold bg-yellow-600 text-xs">إيقاف ⏸</button>
                    <button onclick="panic()" class="px-4 py-2 rounded-xl font-bold bg-red-600 text-xs text-white">تصفية المحفظة 🚨</button>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
                <div class="bg-white/5 p-5 rounded-3xl border border-white/10"><p class="text-gray-500 text-[10px] uppercase mb-1">إجمالي المحفظة</p><div id="total_bal" class="text-2xl font-black font-mono">10,000.00</div></div>
                <div class="bg-white/5 p-5 rounded-3xl border border-white/10"><p class="text-gray-500 text-[10px] uppercase mb-1">صافي الربح ($)</p><div id="pnl_val" class="text-2xl font-black font-mono">0.00</div></div>
                <div class="bg-white/5 p-5 rounded-3xl border border-white/10"><p class="text-gray-500 text-[10px] uppercase mb-1">النسبة المئوية</p><div id="pnl_pct" class="text-2xl font-black font-mono">0%</div></div>
                <div class="bg-white/5 p-5 rounded-3xl border border-white/10 text-center flex flex-col justify-center">
                    <div id="tag" class="text-[10px] text-emerald-500 font-bold mb-1">BOT ACTIVE</div>
                    <div class="h-1.5 w-full bg-gray-800 rounded-full overflow-hidden"><div id="progress" class="h-full bg-emerald-500 w-full animate-pulse"></div></div>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                <div class="bg-white/5 p-6 rounded-3xl border border-emerald-500/20">
                    <h3 class="text-emerald-400 font-bold mb-4 text-sm">🟢 إعدادات الشراء</h3>
                    <select onchange="upd('buy_mode',this.value)" class="bg-gray-800 w-full p-2 rounded mb-3 text-xs border-none outline-none"><option value="fixed">مبلغ ثابت ($)</option><option value="percent">نسبة من المحفظة</option></select>
                    <input type="number" value="100" onchange="upd('buy_value',this.value)" class="bg-gray-800 w-full p-2 rounded text-lg font-bold border-none outline-none">
                </div>
                <div class="bg-white/5 p-6 rounded-3xl border border-red-500/20">
                    <h3 class="text-red-400 font-bold mb-4 text-sm">🔴 إعدادات البيع</h3>
                    <select onchange="upd('sell_mode',this.value)" class="bg-gray-800 w-full p-2 rounded mb-3 text-xs border-none outline-none"><option value="percent">نسبة من العملة</option><option value="fixed">مبلغ ثابت ($)</option></select>
                    <input type="number" value="1.0" step="0.1" onchange="upd('sell_value',this.value)" class="bg-gray-800 w-full p-2 rounded text-lg font-bold border-none outline-none">
                </div>
            </div>

            <div class="bg-white/5 rounded-3xl overflow-hidden border border-white/10">
                <table class="w-full text-sm text-right"><thead class="bg-white/10 text-gray-400 text-[10px]"><tr><th class="p-4 uppercase">الوقت</th><th class="p-4 uppercase">الزوج</th><th class="p-4 uppercase">النوع</th><th class="p-4 uppercase">السعر</th><th class="p-4 uppercase">الحالة</th></tr></thead>
                <tbody id="table" class="divide-y divide-gray-800">
                    <tr><td colspan="5" class="p-10 text-center text-gray-600 font-bold">انتظار إشارة تريدينق فيو...</td></tr>
                </tbody></table>
            </div>
        </div>

        <script>
            let active = true;
            async function upd(k,v) {{ await fetch('/update_settings',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:`key=${{k}}&value=${{v}}` }}); }}
            
            async function toggleBot() {{ 
                active = !active; 
                document.getElementById('p-btn').textContent = active?'إيقاف ⏸':'تشغيل ▶️';
                document.getElementById('p-btn').className = active?'px-4 py-2 rounded-xl font-bold bg-yellow-600 text-xs':'px-4 py-2 rounded-xl font-bold bg-emerald-600 text-xs';
                document.getElementById('tag').textContent = active?'BOT ACTIVE':'BOT PAUSED';
                document.getElementById('tag').className = active?'text-[10px] text-emerald-500 font-bold mb-1':'text-[10px] text-red-500 font-bold mb-1';
                document.getElementById('progress').className = active?'h-full bg-emerald-500 w-full animate-pulse':'h-full bg-red-500 w-full';
                await upd('bot_active',active); 
            }}

            async function panic() {{ if(confirm('⚠️ هل تريد بيع كل العملات المفتوحة والعودة لـ USDT بالكامل؟')) await fetch('/liquidate',{{method:'POST'}}); }}

            const ws = new WebSocket(`${{window.location.protocol==='https:'?'wss:':'ws:'}}//${{window.location.host}}/ws`);
            ws.onmessage = (e) => {{
                const d = JSON.parse(e.data);
                document.getElementById('total_bal').textContent = d.total.toLocaleString();
                document.getElementById('pnl_val').textContent = (d.pnl >= 0 ? '+' : '') + d.pnl;
                document.getElementById('pnl_val').className = d.pnl >= 0 ? 'text-2xl font-black text-emerald-400' : 'text-2xl font-black text-red-400';
                document.getElementById('pnl_pct').textContent = d.pnl_pct + '%';
                
                if(d.trades.length > 0) {{
                    document.getElementById('table').innerHTML = d.trades.map(t => `<tr class="border-b border-gray-800 hover:bg-white/5 transition-colors"><td class="p-4 text-xs text-gray-500 font-mono">${{t.time}}</td><td class="p-4 font-bold text-white text-xs">${{t.pair}}</td><td class="p-4 font-bold text-xs ${{t.action==='buy' || t.action==='شراء'?'text-emerald-400':'text-red-400'}} uppercase">${{t.action}}</td><td class="p-4 text-yellow-500 font-mono font-bold text-xs">${{t.price}}</td><td class="p-4 text-[10px] font-bold text-gray-400">${{t.status}}</td></tr>`).join('');
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

@app.get("/test")
async def test():
    return bot.execute_trade("SOLUSDT", "buy")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
