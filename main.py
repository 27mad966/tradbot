"""
🤖 BINANCE CRYPTO TRADINGVIEW WEBHOOK BOT - النسخة المبسطة والفعالة
يعمل مباشرة من إشارات TradingView بدون تعقيد
"""

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
from datetime import datetime
from collections import deque
import random
import time
import threading
import os

app = FastAPI(title="🤖 Binance TradingView Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

class SimpleTradingBot:
    def __init__(self):
        self.balance = 10000.0
        self.trades = deque(maxlen=50)
        self.websocket_clients = []
    
    def execute_trade(self, pair, direction, signal="TradingView"):
        # حساب المخاطرة 2%
        amount = self.balance * 0.02
        
        # محاكاة تداول واقعية
        entry_price = random.uniform(0.5, 50000)  # سعر العملة الرقمية
        exit_price = entry_price * (1.1 if random.random() > 0.4 else 0.9)
        
        total_cost = amount
        profit_loss = amount * ((exit_price - entry_price) / entry_price)
        self.balance += profit_loss
        
        trade = {
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'pair': pair,
            'direction': direction,
            'amount': round(amount, 2),
            'entry_price': round(entry_price, 4),
            'exit_price': round(exit_price, 4),
            'total_cost': round(total_cost, 2),
            'profit_loss': round(profit_loss, 2),
            'pnl_percent': round((profit_loss/amount)*100, 2),
            'balance_after': round(self.balance, 2),
            'signal': signal
        }
        
        self.trades.appendleft(trade)
        return trade

bot = SimpleTradingBot()

# الصفحة الرئيسية - داشبورد بسيط وفعال
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 Binance TradingView Bot</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
        body { font-family: 'Cairo', sans-serif; }
        .glass { background: rgba(255,255,255,0.1); backdrop-filter: blur(10px); }
    </style>
</head>
<body class="bg-gradient-to-br from-gray-900 to-black text-white min-h-screen">
    <div class="container mx-auto px-6 py-8 max-w-6xl">
        
        <!-- Header -->
        <div class="text-center mb-12">
            <h1 class="text-5xl font-bold bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent mb-4">
                🤖 Binance TradingView Bot
            </h1>
            <p class="text-xl text-gray-300">Webhook جاهز | تنفيذ فوري لإشارات TradingView</p>
            <div class="mt-6 p-4 bg-emerald-500/20 border border-emerald-500/50 rounded-2xl">
                <code class="text-lg font-mono break-all">{{YOUR_RENDER_URL}}/webhook</code>
                <p class="text-sm text-emerald-300 mt-2">انسخ هذا الرابط وضعه في TradingView Alert</p>
            </div>
        </div>

        <!-- الرصيد والإحصائيات -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div class="glass p-8 rounded-3xl text-center shadow-2xl">
                <div class="text-4xl font-bold text-emerald-400 mb-2" id="balance">$10,000</div>
                <div class="text-lg text-gray-300">الرصيد الحالي</div>
            </div>
            <div class="glass p-8 rounded-3xl text-center shadow-2xl">
                <div class="text-3xl font-bold text-blue-400 mb-2" id="total-trades">0</div>
                <div class="text-lg text-gray-300">إجمالي الصفقات</div>
            </div>
            <div class="glass p-8 rounded-3xl text-center shadow-2xl">
                <div class="text-3xl font-bold text-purple-400 mb-2" id="win-rate">0%</div>
                <div class="text-lg text-gray-300">نسبة النجاح</div>
            </div>
        </div>

        <!-- سجل الصفقات -->
        <div class="glass p-8 rounded-3xl shadow-2xl">
            <h2 class="text-3xl font-bold text-center mb-8 text-white">📊 آخر الصفقات</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-right">
                    <thead>
                        <tr class="border-b-2 border-gray-600">
                            <th class="p-4 font-bold text-lg">الوقت</th>
                            <th class="p-4 font-bold text-lg">الزوج</th>
                            <th class="p-4 font-bold text-lg">الاتجاه</th>
                            <th class="p-4 font-bold text-lg">سعر الدخول</th>
                            <th class="p-4 font-bold text-lg">الحجم</th>
                            <th class="p-4 font-bold text-lg">النتيجة</th>
                            <th class="p-4 font-bold text-lg">الرصيد</th>
                        </tr>
                    </thead>
                    <tbody id="trades-table">
                        <tr>
                            <td colspan="7" class="p-12 text-center text-gray-500 text-xl">جاري الانتظار لأول تنبيه TradingView...</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- تعليمات TradingView -->
        <div class="mt-12 p-8 bg-gradient-to-r from-emerald-500/10 to-blue-500/10 border-2 border-emerald-500/30 rounded-3xl">
            <h3 class="text-2xl font-bold text-center mb-6 text-emerald-400">🎯 كيفية الاستخدام</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 text-lg">
                <div>
                    <div class="flex items-center mb-4 p-4 bg-gray-800/50 rounded-xl">
                        <span class="text-2xl mr-4">1️⃣</span>
                        <div>
                            <strong>انسخ Webhook URL</strong><br>
                            <code class="text-sm mt-1">{{YOUR_RENDER_URL}}/webhook</code>
                        </div>
                    </div>
                    <div class="flex items-center p-4 bg-gray-800/50 rounded-xl">
                        <span class="text-2xl mr-4">2️⃣</span>
                        <div>
                            <strong>ضع في TradingView Alert:</strong>
                            <pre class="text-sm mt-2 bg-black p-2 rounded">{"pair": "{{ticker}}", "direction": "BUY"}</pre>
                        </div>
                    </div>
                </div>
                <div>
                    <div class="flex items-center p-4 bg-gray-800/50 rounded-xl">
                        <span class="text-2xl mr-4">3️⃣</span>
                        <strong>التنفيذ التلقائي:</strong><br>
                        <small class="text-emerald-400">2% مخاطرة | محاكاة واقعية | سجل كامل</small>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // WebSocket للتحديث الحي
        const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
        
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            document.getElementById('balance').textContent = '$' + data.balance.toLocaleString();
            document.getElementById('total-trades').textContent = data.total_trades;
            
            const wins = data.trades.filter(t => t.profit_loss > 0).length;
            document.getElementById('win-rate').textContent = (wins/data.total_trades*100 || 0).toFixed(1) + '%';
            
            updateTable(data.trades);
        };

        function updateTable(trades) {
            const tbody = document.getElementById('trades-table');
            if (!trades.length) {
                tbody.innerHTML = '<tr><td colspan="7" class="p-12 text-center text-gray-500 text-xl">جاري الانتظار لأول تنبيه...</td></tr>';
                return;
            }
            
            tbody.innerHTML = trades.map(trade => `
                <tr class="hover:bg-gray-800/50 border-b border-gray-700">
                    <td class="p-4 font-mono text-sm">${trade.time}</td>
                    <td class="p-4 font-bold text-lg">${trade.pair}</td>
                    <td class="p-4">
                        <span class="px-3 py-1 rounded-full text-sm font-bold
                            ${trade.direction === 'BUY' ? 'bg-green-500/30 text-green-400' : 'bg-red-500/30 text-red-400'}">
                            ${trade.direction}
                        </span>
                    </td>
                    <td class="p-4 font-mono">$${trade.entry_price}</td>
                    <td class="p-4 font-bold text-emerald-400">$${trade.amount}</td>
                    <td class="p-4 font-bold ${trade.profit_loss >= 0 ? 'text-green-400' : 'text-red-400'}">
                        ${trade.profit_loss >= 0 ? '✅' : '❌'} $${trade.profit_loss} 
                        <span class="text-sm">(${trade.pnl_percent}%)</span>
                    </td>
                    <td class="p-4 font-bold text-blue-400 text-lg">$${trade.balance_after.toLocaleString()}</td>
                </tr>
            `).join('');
        }

        // Keepalive
        setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) ws.send('ping');
        }, 25000);
    </script>
</body>
</html>
    """)

# WebSocket للتحديث الحي 24/7
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    bot.websocket_clients.append(websocket)
    
    try:
        while True:
            # إرسال البيانات كل ثانية
            data = {
                "balance": bot.balance,
                "total_trades": len(bot.trades),
                "trades": list(bot.trades)
            }
            await websocket.send_json(data)
            await asyncio.sleep(1)
    except:
        bot.websocket_clients.remove(websocket)

# TRADINGVIEW WEBHOOK - الجزء الأساسي!
@app.post("/webhook")
async def tradingview_webhook(request: Request):
    try:
        # استقبال التنبيه من TradingView
        data = await request.json()
        
        pair = data.get("pair", data.get("ticker", "BTCUSDT")).upper().replace("-", "/")
        direction = data.get("direction", data.get("action", "BUY")).upper()
        
        print(f"📨 تنبيه TradingView: {pair} - {direction}")
        
        # تنفيذ الصفقة فوراً
        trade = bot.execute_trade(pair, direction, "TradingView Alert")
        
        print(f"✅ تم التنفيذ: {trade['profit_loss']}")
        
        return {"status": "success", "trade": trade}
        
    except Exception as e:
        print(f"❌ خطأ في Webhook: {e}")
        return {"status": "error", "message": str(e)}

# صفحة اختبار Webhook
@app.get("/test")
async def test_webhook():
    trade = bot.execute_trade("BTC/USDT", "BUY", "Test")
    return {"message": "تم اختبار Webhook بنجاح", "trade": trade}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
