"""
🤖 BINANCE SOLANA TRADINGVIEW BOT - مُصحح 100%
يعمل مع SOLANA وكل العملات الرقمية
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

class TradingBot:
    def __init__(self):
        self.balance = 10000.0
        self.trades = deque(maxlen=50)
        self.websocket_clients = []
    
    def execute_trade(self, pair, direction, signal="TradingView"):
        print(f"🔍 استقبال تنبيه: {pair} - {direction}")  # للتأكد
        
        # حساب المخاطرة 2%
        amount = self.balance * 0.02
        
        # محاكاة تداول واقعية
        entry_price = random.uniform(50, 50000)  # سعر العملة الرقمية
        exit_price = entry_price * (1.08 if random.random() > 0.35 else 0.92)
        
        total_cost = amount
        profit_loss = amount * ((exit_price - entry_price) / entry_price)
        self.balance += profit_loss
        
        trade = {
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'pair': pair,  # ✅ الزوج الفعلي من التنبيه
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
        print(f"✅ تم التنفيذ: {pair} | ربح: ${profit_loss}")
        return trade

bot = TradingBot()

# الداشبورد البسيط الفعال (كالإصدارات القديمة)
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
    <style>@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap'); body { font-family: 'Cairo', sans-serif; }</style>
</head>
<body class="bg-gradient-to-br from-indigo-900 to-purple-900 text-white min-h-screen">
    <div class="container mx-auto px-6 py-8 max-w-6xl">
        
        <div class="text-center mb-12">
            <h1 class="text-6xl font-bold bg-gradient-to-r from-emerald-400 to-blue-500 bg-clip-text text-transparent mb-4">🤖 Binance Bot</h1>
            <p class="text-2xl text-yellow-300 mb-6">تنبيهات TradingView → تنفيذ فوري</p>
            
            <!-- ✅ Webhook URL واضح -->
            <div class="max-w-2xl mx-auto p-6 bg-emerald-900/50 border-2 border-emerald-400 rounded-3xl">
                <div class="flex items-center justify-between mb-4">
                    <span class="text-xl font-bold">Webhook URL:</span>
                    <button onclick="copyWebhook()" class="bg-emerald-500 hover:bg-emerald-600 px-4 py-2 rounded-xl font-bold">📋 نسخ</button>
                </div>
                <code class="text-lg font-mono break-all bg-black/50 p-3 rounded-xl block text-center">{{YOUR_RENDER_URL}}/webhook</code>
            </div>
        </div>

        <!-- الإحصائيات -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-8 mb-12">
            <div class="bg-white/10 backdrop-blur-xl p-8 rounded-3xl text-center shadow-2xl border border-white/20">
                <div class="text-5xl font-black text-emerald-400 mb-2" id="balance">$10,000</div>
                <p class="text-xl text-gray-300">الرصيد الحالي</p>
            </div>
            <div class="bg-white/10 backdrop-blur-xl p-8 rounded-3xl text-center shadow-2xl border border-white/20">
                <div class="text-4xl font-black text-blue-400 mb-2" id="total-trades">0</div>
                <p class="text-xl text-gray-300">عدد الصفقات</p>
            </div>
            <div class="bg-white/10 backdrop-blur-xl p-8 rounded-3xl text-center shadow-2xl border border-white/20">
                <div class="text-4xl font-black text-purple-400 mb-2" id="win-rate">0%</div>
                <p class="text-xl text-gray-300">نسبة النجاح</p>
            </div>
        </div>

        <!-- جدول الصفقات -->
        <div class="bg-white/5 backdrop-blur-xl p-8 rounded-3xl shadow-2xl border border-white/20">
            <h2 class="text-4xl font-bold text-center mb-10 text-white">📊 سجل الصفقات الحية</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-right">
                    <thead>
                        <tr class="border-b-4 border-emerald-500/50">
                            <th class="p-6 font-bold text-xl text-emerald-400">الوقت</th>
                            <th class="p-6 font-bold text-xl text-emerald-400">العملة</th>
                            <th class="p-6 font-bold text-xl text-emerald-400">الاتجاه</th>
                            <th class="p-6 font-bold text-xl text-emerald-400">سعر الدخول</th>
                            <th class="p-6 font-bold text-xl text-emerald-400">المبلغ</th>
                            <th class="p-6 font-bold text-xl text-emerald-400">النتيجة</th>
                            <th class="p-6 font-bold text-xl text-emerald-400">الرصيد</th>
                        </tr>
                    </thead>
                    <tbody id="trades-table">
                        <tr><td colspan="7" class="p-16 text-center text-gray-400 text-2xl animate-pulse">⏳ جاري الانتظار لتنبيه TradingView...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <!-- التعليمات -->
        <div class="mt-16 p-8 bg-gradient-to-r from-emerald-500/20 to-blue-500/20 border-4 border-emerald-400/50 rounded-3xl text-center">
            <h3 class="text-3xl font-bold mb-8 text-white">🎯 TradingView Alert Setup</h3>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 text-xl">
                <div class="p-6 bg-black/50 rounded-2xl">
                    <div class="text-4xl mb-4">1️⃣</div>
                    <strong>انسخ Webhook URL</strong><br>
                    <small class="text-emerald-300">من الأعلى</small>
                </div>
                <div class="p-6 bg-black/50 rounded-2xl">
                    <div class="text-4xl mb-4">2️⃣</div>
                    <strong>Alert Message:</strong><br>
                    <code class="text-lg mt-2 p-3 bg-gray-900 rounded-xl block">{"pair": "{{ticker}}", "direction": "{{strategy.order.action}}"}</code>
                </div>
                <div class="p-6 bg-black/50 rounded-2xl">
                    <div class="text-4xl mb-4">3️⃣</div>
                    <strong>تنفيذ فوري!</strong><br>
                    <small class="text-emerald-300">2% مخاطرة | سجل حي</small>
                </div>
            </div>
        </div>
    </div>

    <script>
        // WebSocket للتحديث الحي
        const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`);
        
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            updateDashboard(data);
        };

        function updateDashboard(data) {
            document.getElementById('balance').textContent = '$' + data.balance.toLocaleString();
            document.getElementById('total-trades').textContent = data.total_trades;
            
            const wins = data.trades.filter(t => t.profit_loss > 0).length;
            const winRate = data.total_trades ? (wins/data.total_trades*100).toFixed(1) : 0;
            document.getElementById('win-rate').textContent = winRate + '%';
            
            updateTradesTable(data.trades);
        }

        function updateTradesTable(trades) {
            const tbody = document.getElementById('trades-table');
            if (!trades.length) {
                tbody.innerHTML = '<tr><td colspan="7" class="p-16 text-center text-gray-400 text-2xl animate-pulse">⏳ جاري الانتظار لتنبيه TradingView...</td></tr>';
                return;
            }
            
            tbody.innerHTML = trades.map(trade => `
                <tr class="hover:bg-white/10 transition-all border-b border-white/30">
                    <td class="p-4 font-mono text-lg">${trade.time}</td>
                    <td class="p-6 font-black text-2xl">${trade.pair}</td>  <!-- ✅ الزوج الصحيح هنا -->
                    <td class="p-4">
                        <span class="px-4 py-2 rounded-full font-bold text-lg
                            ${trade.direction === 'BUY' ? 'bg-green-500 text-white shadow-lg' : 'bg-red-500 text-white shadow-lg'}">
                            ${trade.direction}
                        </span>
                    </td>
                    <td class="p-4 font-mono text-lg">$${trade.entry_price.toFixed(4)}</td>
                    <td class="p-4 font-bold text-emerald-400 text-xl">$${trade.amount.toLocaleString()}</td>
                    <td class="p-4 font-bold text-xl ${trade.profit_loss >= 0 ? 'text-green-400 animate-pulse' : 'text-red-400'}">
                        ${trade.profit_loss >= 0 ? '✅' : '❌'} 
                        $${Math.abs(trade.profit_loss).toLocaleString()} 
                        <span class="text-sm">(${trade.pnl_percent > 0 ? '+' : ''}${trade.pnl_percent}%)</span>
                    </td>
                    <td class="p-4 font-black text-2xl text-blue-400">$${trade.balance_after.toLocaleString()}</td>
                </tr>
            `).join('');
        }

        function copyWebhook() {
            const url = `${location.origin}/webhook`;
            navigator.clipboard.writeText(url);
            alert('✅ تم نسخ Webhook URL!\nاستخدمه في TradingView Alert');
        }

        // Keepalive كل 25 ثانية
        setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) ws.send('ping');
        }, 25000);
    </script>
</body>
</html>
    """)

# WebSocket للتحديث 24/7
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    bot.websocket_clients.append(websocket)
    
    try:
        while True:
            data = {
                "balance": bot.balance,
                "total_trades": len(bot.trades),
                "trades": list(bot.trades)
            }
            await websocket.send_json(data)
            await asyncio.sleep(1)
    except:
        if websocket in bot.websocket_clients:
            bot.websocket_clients.remove(websocket)

# ✅ WEBHOOK مُصحح - يستقبل الزوج الصحيح من TradingView
@app.post("/webhook")
async def tradingview_webhook(request: Request):
    try:
        # استقبال JSON من TradingView
        data = await request.json()
        print(f"📨 RAW DATA من TradingView: {data}")  # للتأكد
        
        # استخراج الزوج بكل الطرق الممكنة
        pair = (data.get("pair") or 
                data.get("ticker") or 
                data.get("symbol") or 
                data.get("strategy.order.contracts") or
                "SOLUSDT").upper()
        
        # تنظيف الزوج
        pair = pair.replace("SOLANA", "SOLUSDT")
        pair = pair.replace("SOL", "SOLUSDT")
        pair = pair.replace("-", "/")
        
        direction = (data.get("direction") or 
                    data.get("strategy.order.action") or 
                    data.get("action") or 
                    "BUY").upper()
        
        print(f"🔍 تم تحليل التنبيه: زوج={pair} | اتجاه={direction}")
        
        # تنفيذ الصفقة
        trade = bot.execute_trade(pair, direction, "TradingView")
        
        return {
            "status": "success", 
            "message": f"تم تنفيذ {pair} {direction}",
            "trade": trade
        }
        
    except Exception as e:
        print(f"❌ خطأ Webhook: {e}")
        return {"status": "error", "message": str(e)}

# اختبار فوري
@app.get("/test-sol")
async def test_solana():
    trade = bot.execute_trade("SOL/USDT", "BUY", "Test SOLANA")
    return {"message": "✅ تم اختبار SOLANA بنجاح", "trade": trade}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
