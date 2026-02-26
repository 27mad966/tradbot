import os
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
from datetime import datetime
from collections import deque
import asyncio
import ccxt

app = FastAPI(title="🤖 Binance TradingView Bot")

# إعدادات الأمان والربط عبر متغيرات البيئة
DASHBOARD_PASS = "AHMED_BOSS_2026"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# --- محرك التداول الحقيقي (قراءة من Environment) ---
class TradingBot:
    def __init__(self):
        # جلب المفاتيح من Render Environment Variables
        api_key = os.getenv("BINANCE_API_KEY")
        secret_key = os.getenv("BINANCE_SECRET_KEY")
        
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
                'recvWindow': 60000
            }
        })
        # تفعيل وضع التجربة تلقائياً
        self.exchange.set_sandbox_mode(True)
        self.trades = deque(maxlen=50)
        self.balance = 0.0

    async def update_balance(self):
        try:
            # التأكد من وجود المفاتيح قبل المحاولة
            if self.exchange.apiKey and self.exchange.secret:
                bal = self.exchange.fetch_balance()
                self.balance = bal['total'].get('USDT', 0.0)
        except Exception as e:
            print(f"Balance Update Error: {e}")
            self.balance = 0.0

    def execute_real_trade(self, pair, direction):
        # تنظيف اسم الزوج من أي أخطاء تكرار
        pair_clean = pair.replace("USDTUSDT", "USDT").upper()
        # تنسيق الزوج ليتناسب مع CCXT (مثال: SOL/USDT)
        if "/" not in pair_clean and "USDT" in pair_clean:
            base = pair_clean.replace("USDT", "")
            pair_formatted = f"{base}/USDT"
        else:
            pair_formatted = pair_clean

        try:
            amount_usdt = 100.0  # قيمة الصفقة
            ticker = self.exchange.fetch_ticker(pair_formatted)
            amount_coin = amount_usdt / ticker['last']
            
            action = direction.upper()
            if "BUY" in action or "LONG" in action:
                order = self.exchange.create_market_buy_order(pair_formatted, amount_coin)
                final_action = "شراء"
            else:
                order = self.exchange.create_market_sell_order(pair_formatted, amount_coin)
                final_action = "بيع"
            
            trade_entry = {
                'time': datetime.now().strftime("%H:%M:%S"),
                'pair': pair_formatted,
                'action': final_action,
                'entry_price': round(ticker['last'], 4),
                'status': "✅ ناجح"
            }
            self.trades.appendleft(trade_entry)
            return trade_entry
        except Exception as e:
            error_entry = {
                'time': datetime.now().strftime("%H:%M:%S"),
                'pair': pair_formatted,
                'action': "خطأ",
                'entry_price': 0,
                'status': f"❌ {str(e)[:20]}"
            }
            self.trades.appendleft(error_entry)
            return error_entry

bot = TradingBot()

# --- الواجهة البرمجية (Dashboard) ---
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    # استخدام التصميم الاحترافي الخاص بك مع ربط البيانات الحية
    return HTMLResponse(f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>Sovereign Bot v2.1</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;700;900&display=swap');
        body {{ font-family: 'Cairo', sans-serif; background-color: #0b0e11; }}
        .glass {{ background: rgba(23, 27, 34, 0.8); backdrop-filter: blur(12px); border: 1px solid #30363d; }}
    </style>
</head>
<body class="text-gray-100 p-4 md:p-10">
    <div class="max-w-5xl mx-auto">
        <header class="text-center mb-12">
            <h1 class="text-5xl font-black text-transparent bg-clip-text bg-gradient-to-r from-yellow-400 to-orange-500 mb-4">
                SOVEREIGN STATION
            </h1>
            <div class="inline-block px-4 py-1 rounded-full bg-yellow-400/10 border border-yellow-400/20 text-yellow-400 text-sm">
                Mode: Binance Demo (Production Secure)
            </div>
        </header>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <div class="glass p-8 rounded-3xl">
                <p class="text-gray-400 text-sm mb-1 uppercase">رصيد الحساب (USDT)</p>
                <div class="text-4xl font-black text-white" id="balance">0.00</div>
            </div>
            <div class="glass p-8 rounded-3xl">
                <p class="text-gray-400 text-sm mb-1 uppercase">إجمالي العمليات</p>
                <div class="text-4xl font-black text-blue-400" id="total-trades">0</div>
            </div>
        </div>

        <div class="glass rounded-3xl overflow-hidden shadow-2xl">
            <div class="p-6 border-b border-gray-800 flex justify-between items-center">
                <h2 class="text-xl font-bold">📊 سجل العمليات الحية</h2>
                <span class="text-xs text-green-400 animate-pulse">● Live Feed</span>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-right">
                    <thead class="bg-black/20 text-gray-400 text-sm">
                        <tr>
                            <th class="p-4">الوقت</th>
                            <th class="p-4">الزوج</th>
                            <th class="p-4">العملية</th>
                            <th class="p-4">السعر</th>
                            <th class="p-4">الحالة</th>
                        </tr>
                    </thead>
                    <tbody id="trades-table" class="divide-y divide-gray-800">
                        <tr><td colspan="5" class="p-10 text-center text-gray-600">بانتظار الإشارة الأولى...</td></tr>
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
            document.getElementById('balance').textContent = data.balance.toLocaleString(undefined, {{minimumFractionDigits: 2}});
            document.getElementById('total-trades').textContent = data.total_trades;
            
            const tbody = document.getElementById('trades-table');
            if (data.trades.length > 0) {{
                tbody.innerHTML = data.trades.map(t => `
                    <tr class="hover:bg-white/5 transition-colors">
                        <td class="p-4 text-gray-500 font-mono text-sm">${{t.time}}</td>
                        <td class="p-4 font-bold text-white">${{t.pair}}</td>
                        <td class="p-4">
                            <span class="px-3 py-1 rounded-lg text-xs font-bold ${{t.action === 'شراء' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}}">
                                ${{t.action}}
                            </span>
                        </td>
                        <td class="p-4 font-mono text-yellow-500">${{t.entry_price}}</td>
                        <td class="p-4 text-xs">${{t.status}}</td>
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
            await websocket.send_json({
                "balance": bot.balance,
                "total_trades": len(bot.trades),
                "trades": list(bot.trades)
            })
            await asyncio.sleep(3)
    except:
        pass

@app.post("/webhook")
async def tradingview_webhook(request: Request):
    try:
        data = await request.json()
        pair = data.get("pair") or data.get("ticker", "SOLUSDT")
        direction = data.get("direction") or data.get("action", "BUY")
        
        result = bot.execute_real_trade(pair, direction)
        return {"status": "processed", "executed": result}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
