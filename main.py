import os
import json
import asyncio
import ccxt
from datetime import datetime
from collections import deque
from fastapi import FastAPI, Request, WebSocket, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="🤖 Sovereign Station v3.3")

# إعدادات الأمان
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

class TradingBot:
    def __init__(self):
        # سحب المتغيرات من ريندر (تأكد من تسميتها BINANCE_API_KEY و BINANCE_SECRET_KEY)
        self.api_key = os.getenv("BINANCE_API_KEY", "").strip()
        self.secret_key = os.getenv("BINANCE_SECRET_KEY", "").strip()
        
        self.exchange = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.secret_key,
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True, # مزامنة الوقت لحل مشكلة الصلاحية
                'recvWindow': 60000, 
                'defaultType': 'spot'
            }
        })
        
        # روابط التست نت الأصلية
        self.exchange.urls['api']['public'] = 'https://testnet.binance.vision/api'
        self.exchange.urls['api']['private'] = 'https://testnet.binance.vision/api'
        
        self.trades = deque(maxlen=50)
        self.balance = 0.0
        self.active_symbol = "USDT"

    async def update_balance(self):
        try:
            if not self.api_key or not self.secret_key:
                self.balance = -1 # المفاتيح مفقودة
                return
            
            # محاولة جلب الرصيد مع تحديث الأسواق للمزامنة
            bal = self.exchange.fetch_balance()
            active = {k: v['total'] for k, v in bal['total'].items() if v > 0}
            
            if "USDT" in active:
                self.balance = active["USDT"]
                self.active_symbol = "USDT"
            elif active:
                self.active_symbol = list(active.keys())[0]
                self.balance = active[self.active_symbol]
            else:
                self.balance = 0.0
        except Exception as e:
            print(f"Connection Error: {e}")
            self.balance = -2 # خطأ في الصلاحية

    def execute_trade(self, pair, direction):
        pair = pair.replace("USDTUSDT", "USDT").upper()
        if "/" not in pair: 
            pair = f"{pair[:-4]}/USDT" if pair.endswith("USDT") else f"{pair}/USDT"
        
        try:
            ticker = self.exchange.fetch_ticker(pair)
            price = ticker['last']
            amount_coin = 100.0 / price
            
            if direction.lower() in ["buy", "long"]:
                self.exchange.create_market_buy_order(pair, amount_coin)
                action = "شراء"
            else:
                self.exchange.create_market_sell_order(pair, amount_coin)
                action = "بيع"
            
            entry = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': action, 'price': round(price, 4), 'status': "✅ ناجح"}
            self.trades.appendleft(entry)
            return entry
        except Exception as e:
            entry = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': "خطأ", 'price': 0, 'status': f"❌ {str(e)[:30]}"}
            self.trades.appendleft(entry)
            return entry

bot = TradingBot()

# --- إصلاح مسار الداشبورد الرئيسي ---
@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>Sovereign Bot Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap');
            body {{ font-family: 'Cairo', sans-serif; background: #0b0e11; color: white; }}
            .glass {{ background: rgba(23, 27, 34, 0.95); border: 1px solid #30363d; backdrop-filter: blur(10px); }}
        </style>
    </head>
    <body class="p-4 md:p-10">
        <div class="max-w-5xl mx-auto text-center">
            <h1 class="text-5xl font-black text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-blue-500 mb-10">SOVEREIGN STATION</h1>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                <div class="glass p-8 rounded-3xl">
                    <p class="text-gray-500 text-sm mb-2 uppercase">الرصيد المتاح</p>
                    <div class="text-4xl font-black text-white"><span id="balance">جاري التحميل...</span> <span id="symbol" class="text-xl"></span></div>
                </div>
                <div class="glass p-8 rounded-3xl">
                    <p class="text-gray-500 text-sm mb-2 uppercase">إجمالي العمليات</p>
                    <div class="text-4xl font-black text-blue-400" id="total-trades">0</div>
                </div>
            </div>
            <div class="glass rounded-3xl overflow-hidden shadow-2xl text-right">
                <div class="p-6 border-b border-gray-800 flex justify-between items-center">
                    <h2 class="font-bold text-xl">📊 سجل العمليات الحية</h2>
                    <span class="text-green-500 text-xs animate-pulse">● متصل</span>
                </div>
                <div class="overflow-x-auto">
                    <table class="w-full">
                        <thead class="bg-white/5 text-gray-400">
                            <tr><th class="p-4">الوقت</th><th class="p-4">الزوج</th><th class="p-4">العملية</th><th class="p-4">السعر</th><th class="p-4">الحالة</th></tr>
                        </thead>
                        <tbody id="trades-table" class="divide-y divide-gray-800">
                            <tr><td colspan="5" class="p-10 text-center text-gray-600">انتظار البيانات...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        <script>
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const ws = new WebSocket(`${{protocol}}//${{window.location.host}}/ws`);
            ws.onmessage = function(event) {{
                const data = JSON.parse(event.data);
                const bal = document.getElementById('balance');
                if (data.balance === -1) bal.textContent = "❌ خطأ في قراءة ريندر";
                else if (data.balance === -2) bal.textContent = "⚠️ خطأ في صلاحية المفاتيح";
                else {{
                    bal.textContent = data.balance.toLocaleString();
                    document.getElementById('symbol').textContent = data.symbol;
                }}
                document.getElementById('total-trades').textContent = data.total_trades;
                const tbody = document.getElementById('trades-table');
                if (data.trades.length > 0) {{
                    tbody.innerHTML = data.trades.map(t => `
                        <tr class="hover:bg-white/5 border-b border-gray-800">
                            <td class="p-4 text-gray-500 font-mono text-xs">${{t.time}}</td>
                            <td class="p-4 font-bold">${{t.pair}}</td>
                            <td class="p-4"><span class="px-3 py-1 rounded-full text-xs font-bold ${{t.action === 'شراء' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}}">${{t.action}}</span></td>
                            <td class="p-4 font-mono text-yellow-500 font-bold">${{t.price}}</td>
                            <td class="p-4 text-xs font-bold text-emerald-400">${{t.status}}</td>
                        </tr>
                    `).join('');
                }}
            }};
        </script>
    </body>
    </html>
    """)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await bot.update_balance()
            await websocket.send_json({"balance": bot.balance, "symbol": bot.active_symbol, "total_trades": len(bot.trades), "trades": list(bot.trades)})
            await asyncio.sleep(3)
    except: pass

class Signal(BaseModel):
    pair: str
    direction: str

@app.post("/webhook")
async def handle_webhook(signal: Signal):
    return bot.execute_trade(signal.pair, signal.direction)

@app.get("/test")
async def test_bot():
    return bot.execute_trade("SOLUSDT", "buy")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
