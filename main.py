"""
نظام تداول آلي مع لوحة تحكم HTML كاملة مدمجة
يعمل مباشرة على Render.com بدون صفحة فاضية
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import uvicorn
import random
from datetime import datetime
import threading
import time
from collections import deque

app = FastAPI(title="🤖 Trading Bot Dashboard")

# تمكين CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Trade(BaseModel):
    time: str
    pair: str
    direction: str
    amount: float
    result: str
    balance_after: float

class TradingBot:
    def __init__(self):
        self.balance = 10000.0
        self.initial_balance = self.balance
        self.trades: deque = deque(maxlen=100)
        self.is_trading = False
        self.lock = threading.Lock()
    
    def execute_trade(self, pair: str, direction: str, amount: float) -> Dict[str, Any]:
        with self.lock:
            if amount > self.balance:
                return {"success": False, "message": "الرصيد غير كافي"}
            
            success_rate = 0.65
            win = random.random() < success_rate
            
            if win:
                profit = amount * random.uniform(0.75, 1.5)
                self.balance += profit
                result = f"✅ ربح: ${profit:.2f}"
            else:
                loss = amount * random.uniform(0.5, 0.95)
                self.balance -= loss
                result = f"❌ خسارة: ${loss:.2f}"
            
            trade = Trade(
                time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                pair=pair,
                direction=direction,
                amount=amount,
                result=result,
                balance_after=self.balance
            )
            self.trades.append(trade)
            
            return {
                "success": True,
                "result": result,
                "balance": self.balance,
                "trade": trade
            }

bot = TradingBot()

# ✅ الصفحة الرئيسية - لوحة التحكم الكاملة
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_content = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🤖 نظام التداول الآلي - لوحة التحكم</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700&display=swap');
            body { font-family: 'Cairo', sans-serif; }
            .gradient-bg { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
            .trade-win { background: linear-gradient(135deg, #10b981, #059669); }
            .trade-loss { background: linear-gradient(135deg, #ef4444, #dc2626); }
            .pulse { animation: pulse 2s infinite; }
        </style>
    </head>
    <body class="bg-gray-900 text-white min-h-screen">
        <div class="container mx-auto px-4 py-8">
            <!-- Header -->
            <div class="text-center mb-12">
                <h1 class="text-5xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent mb-4">
                    🤖 نظام التداول الآلي
                </h1>
                <p class="text-xl text-gray-300">لوحة تحكم شاملة لمراقبة التداول في الوقت الحقيقي</p>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
                <!-- الرصيد -->
                <div id="balance-card" class="bg-gradient-to-br from-blue-600 to-blue-800 p-8 rounded-2xl shadow-2xl">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-blue-200 text-lg">الرصيد الحالي</p>
                            <p id="current-balance" class="text-4xl font-bold text-white mt-2">$10,000.00</p>
                            <p id="pnl-percent" class="text-2xl font-bold mt-2">+0.00%</p>
                        </div>
                        <div class="w-20 h-20 bg-white/20 rounded-2xl flex items-center justify-center">
                            💰
                        </div>
                    </div>
                </div>

                <!-- الإحصائيات -->
                <div id="stats-card" class="bg-gradient-to-br from-purple-600 to-purple-800 p-8 rounded-2xl shadow-2xl">
                    <h3 class="text-xl font-bold mb-6">📊 الإحصائيات</h3>
                    <div class="space-y-3">
                        <div class="flex justify-between">
                            <span>إجمالي الصفقات</span>
                            <span id="total-trades">0</span>
                        </div>
                        <div class="flex justify-between">
                            <span>نسبة الفوز</span>
                            <span id="win-rate">0%</span>
                        </div>
                        <div class="flex justify-between">
                            <span>الربح/الخسارة</span>
                            <span id="pnl">$0.00</span>
                        </div>
                    </div>
                </div>

                <!-- حالة التداول -->
                <div id="status-card" class="bg-gradient-to-br from-gray-700 to-gray-900 p-8 rounded-2xl shadow-2xl">
                    <div class="flex items-center justify-between mb-6">
                        <h3 class="text-xl font-bold">⚙️ حالة النظام</h3>
                    </div>
                    <div class="flex items-center justify-between">
                        <span id="trading-status">🔴 متوقف</span>
                        <button onclick="startTrading()" id="start-btn" 
                                class="bg-green-500 hover:bg-green-600 text-white px-6 py-2 rounded-xl font-bold transition-all">
                            ▶️ بدء التداول
                        </button>
                    </div>
                </div>

                <!-- آخر صفقة -->
                <div id="last-trade-card" class="bg-gradient-to-br from-indigo-600 to-indigo-800 p-8 rounded-2xl shadow-2xl">
                    <h3 class="text-xl font-bold mb-4">🎯 آخر صفقة</h3>
                    <div id="last-trade" class="text-center py-4 bg-black/30 rounded-xl">
                        لا توجد صفقات بعد
                    </div>
                </div>
            </div>

            <!-- أزرار التحكم -->
            <div class="bg-gradient-to-r from-gray-800 to-gray-900 p-8 rounded-2xl shadow-2xl mb-8">
                <div class="flex flex-col lg:flex-row gap-4 justify-center items-center">
                    <div class="flex gap-4">
                        <select id="pair-select" class="bg-gray-700 text-white px-4 py-2 rounded-xl">
                            <option>EUR/USD</option>
                            <option>GBP/USD</option>
                            <option>USD/JPY</option>
                            <option>BTC/USD</option>
                            <option>ETH/USD</option>
                        </select>
                        <select id="direction-select" class="bg-gray-700 text-white px-4 py-2 rounded-xl">
                            <option>CALL</option>
                            <option>PUT</option>
                        </select>
                        <input id="amount-input" type="number" value="100" min="10" max="1000"
                               class="bg-gray-700 text-white px-4 py-2 rounded-xl w-24 text-center">
                    </div>
                    <button onclick="manualTrade()" 
                            class="bg-gradient-to-r from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700 
                                   text-white px-8 py-3 rounded-xl font-bold text-lg shadow-2xl hover:shadow-3xl transition-all">
                        🎯 تنفيذ صفقة يدوية
                    </button>
                </div>
            </div>

            <!-- جدول الصفقات -->
            <div class="bg-gradient-to-r from-gray-800 to-gray-900 p-8 rounded-2xl shadow-2xl">
                <h3 class="text-2xl font-bold mb-8 text-center">📋 سجل آخر 20 صفقة</h3>
                <div class="overflow-x-auto">
                    <table class="w-full text-right">
                        <thead>
                            <tr class="border-b-2 border-gray-700">
                                <th class="p-4 font-bold">الوقت</th>
                                <th class="p-4 font-bold">الزوج</th>
                                <th class="p-4 font-bold">الاتجاه</th>
                                <th class="p-4 font-bold">المبلغ</th>
                                <th class="p-4 font-bold">النتيجة</th>
                                <th class="p-4 font-bold">الرصيد بعد</th>
                            </tr>
                        </thead>
                        <tbody id="trades-table">
                            <tr><td colspan="6" class="p-8 text-center text-gray-500">جاري التحميل...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <script>
            let refreshInterval;

            async function updateDashboard() {
                try {
                    const res = await fetch('/api/dashboard');
                    const data = await res.json();
                    
                    // تحديث الرصيد
                    document.getElementById('current-balance').textContent = `$${data.balance.toLocaleString()}`;
                    const pnlPercent = data.pnl_percent;
                    document.getElementById('pnl-percent').textContent = `${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%`;
                    document.getElementById('pnl-percent').className = 
                        pnlPercent >= 0 ? 'text-2xl font-bold mt-2 text-green-400' : 'text-2xl font-bold mt-2 text-red-400';
                    
                    // تحديث الإحصائيات
                    document.getElementById('total-trades').textContent = data.total_trades;
                    document.getElementById('win-rate').textContent = data.win_rate;
                    document.getElementById('pnl').textContent = `$${data.pnl.toFixed(2)}`;
                    
                    // حالة التداول
                    document.getElementById('trading-status').textContent = data.trading_status ? '🟢 يعمل' : '🔴 متوقف';
                    
                    // آخر صفقة
                    if (data.recent_trades.length > 0) {
                        const last = data.recent_trades[data.recent_trades.length - 1];
                        document.getElementById('last-trade').innerHTML = `
                            <div class="p-4">
                                <div class="font-bold text-lg">${last.pair} - ${last.direction}</div>
                                <div class="text-2xl font-bold ${last.result.includes('✅') ? 'text-green-400' : 'text-red-400'}">
                                    ${last.result}
                                </div>
                                <div class="text-sm text-gray-300 mt-2">${last.time}</div>
                            </div>
                        `;
                    }
                    
                    // جدول الصفقات
                    updateTradesTable(data.recent_trades);
                    
                } catch (error) {
                    console.error('خطأ في تحديث لوحة التحكم:', error);
                }
            }

            function updateTradesTable(trades) {
                const tbody = document.getElementById('trades-table');
                if (trades.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="p-8 text-center text-gray-500">لا توجد صفقات بعد</td></tr>';
                    return;
                }
                
                tbody.innerHTML = trades.slice(-20).map(trade => `
                    <tr class="hover:bg-gray-800/50 transition-all border-b border-gray-800">
                        <td class="p-4">${trade.time}</td>
                        <td class="p-4 font-bold">${trade.pair}</td>
                        <td class="p-4">
                            <span class="px-3 py-1 rounded-full text-sm font-bold
                                ${trade.direction === 'CALL' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}">
                                ${trade.direction}
                            </span>
                        </td>
                        <td class="p-4 font-bold text-green-400">$${trade.amount.toFixed(2)}</td>
                        <td class="p-4">
                            <span class="px-4 py-2 rounded-xl font-bold text-lg font-mono
                                ${trade.result.includes('✅') ? 'trade-win text-white shadow-lg' : 'trade-loss text-white shadow-lg'}">
                                ${trade.result}
                            </span>
                        </td>
                        <td class="p-4 font-bold text-blue-400">$${trade.balance_after.toLocaleString()}</td>
                    </tr>
                `).join('');
            }

            async function startTrading() {
                await fetch('/api/trade/start');
                updateDashboard();
            }

            async function stopTrading() {
                await fetch('/api/trade/stop');
                updateDashboard();
            }

            async function manualTrade() {
                const pair = document.getElementById('pair-select').value;
                const direction = document.getElementById('direction-select').value;
                const amount = parseFloat(document.getElementById('amount-input').value);
                
                await fetch('/api/trade/manual', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({pair, direction, amount})
                });
                updateDashboard();
            }

            // بدء التحديث التلقائي
            refreshInterval = setInterval(updateDashboard, 2000);
            updateDashboard();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# باقي الـ APIs
@app.get("/api/dashboard")
async def get_dashboard():
    total_trades = len(bot.trades)
    wins = sum(1 for trade in bot.trades if "✅" in trade.result)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    return {
        "balance": round(bot.balance, 2),
        "pnl": round(bot.balance - bot.initial_balance, 2),
        "pnl_percent": round(((bot.balance - bot.initial_balance) / bot.initial_balance) * 100, 2),
        "total_trades": total_trades,
        "win_rate": f"{win_rate:.1f}%",
        "trading_status": bot.is_trading,
        "recent_trades": list(bot.trades)
    }

@app.get("/api/balance")
async def get_balance():
    pnl = bot.balance - bot.initial_balance
    return {
        "balance": round(bot.balance, 2),
        "initial_balance": round(bot.initial_balance, 2),
        "pnl": round(pnl, 2),
        "pnl_percent": round((pnl / bot.initial_balance) * 100, 2)
    }

@app.get("/api/trades")
async def get_trades():
    return list(bot.trades)

@app.post("/api/trade/manual")
async def manual_trade(pair: str, direction: str, amount: float):
    result = bot.execute_trade(pair, direction, amount)
    return result

@app.get("/api/trade/start")
async def start_trading():
    if not bot.is_trading:
        bot.is_trading = True
        threading.Thread(target=auto_trading_loop, daemon=True).start()
        return {"status": "started", "message": "✅ بدأ التداول التلقائي"}
    return {"status": "already_running", "message": "⏹️ التداول يعمل بالفعل"}

@app.get("/api/trade/stop")
async def stop_trading():
    bot.is_trading = False
    return {"status": "stopped", "message": "⏹️ توقف التداول التلقائي"}

def auto_trading_loop():
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "ETH/USD"]
    directions = ["CALL", "PUT"]
    
    while bot.is_trading:
        try:
            pair = random.choice(pairs)
            direction = random.choice(directions)
            amount = round(random.uniform(25, 100), 2)
            bot.execute_trade(pair, direction, amount)
            time.sleep(5)
        except Exception as e:
            print(f"خطأ في التداول: {e}")
            time.sleep(1)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
