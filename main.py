"""
🤖 نظام تداول TradingView Strategy Bot - النسخة الاحترافية
تحديد الأزواج + الاستراتيجية + إدارة المخاطر الكاملة
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uvicorn
import random
from datetime import datetime
import threading
import time
import json
from collections import deque

app = FastAPI(title="🤖 TradingView Strategy Bot")

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
    risk_percent: float
    result: str
    balance_after: float
    strategy_signal: str

class TradingBot:
    def __init__(self):
        self.balance = 10000.0
        self.initial_balance = self.balance
        self.trades: deque = deque(maxlen=200)
        self.is_trading = False
        self.lock = threading.Lock()
        self.trading_thread = None
        
        # ✅ إعدادات الاستراتيجية الخاصة بك
        self.user_pairs = []  # الأزواج التي تحددها أنت
        self.risk_per_trade = 0.02  # 2% مخاطرة لكل صفقة
        self.max_daily_trades = 5
        self.daily_trades = 0
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0)
    
    def set_user_pairs(self, pairs: List[str]):
        """تحديد الأزواج من TradingView"""
        self.user_pairs = pairs
    
    def calculate_position_size(self, pair: str) -> float:
        """حساب حجم الصفقة حسب نسبة المخاطرة"""
        risk_amount = self.balance * self.risk_per_trade
        return round(risk_amount, 2)
    
    def execute_trade(self, pair: str, direction: str, signal: str = "Manual") -> Dict[str, Any]:
        with self.lock:
            if not self.user_pairs or pair not in self.user_pairs:
                return {"success": False, "message": f"🚫 الزوج {pair} غير محدد في استراتيجيتك"}
            
            # التحقق من حد الصفقات اليومية
            if self.daily_trades >= self.max_daily_trades:
                return {"success": False, "message": "🚫 حد الصفقات اليومية وصل"}
            
            amount = self.calculate_position_size(pair)
            if amount > self.balance * 0.1:  # لا تتجاوز 10% من الرصيد
                amount = self.balance * 0.1
            
            if amount > self.balance:
                return {"success": False, "message": "الرصيد غير كافي"}
            
            # محاكاة إشارة TradingView (65% نجاح)
            success_rate = 0.65
            win = random.random() < success_rate
            
            if win:
                profit = amount * random.uniform(1.2, 2.5)  # ربح أعلى
                self.balance += profit
                result = f"✅ ربح: +${profit:.2f}"
            else:
                loss = amount * random.uniform(0.8, 1.0)
                self.balance -= loss
                result = f"❌ خسارة: -${loss:.2f}"
            
            # زيادة عداد الصفقات اليومية
            self.daily_trades += 1
            
            trade = Trade(
                time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                pair=pair,
                direction=direction,
                amount=amount,
                risk_percent=self.risk_per_trade * 100,
                result=result,
                balance_after=self.balance,
                strategy_signal=signal
            )
            self.trades.append(trade)
            
            return {
                "success": True,
                "result": result,
                "balance": self.balance,
                "trade": trade
            }
    
    def reset_daily_counter(self):
        """إعادة تعيين عداد الصفقات اليومية"""
        now = datetime.now()
        if now.date() > self.daily_reset_time.date():
            self.daily_trades = 0
            self.daily_reset_time = now.replace(hour=0, minute=0, second=0)

bot = TradingBot()

# الصفحة الرئيسية - لوحة تحكم احترافية
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_content = """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>🤖 TradingView Strategy Bot</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700;900&display=swap');
            body { font-family: 'Cairo', sans-serif; }
            .gradient-gold { background: linear-gradient(135deg, #f59e0b, #d97706); }
            .trade-win { background: linear-gradient(135deg, #10b981, #059669); }
            .trade-loss { background: linear-gradient(135deg, #ef4444, #dc2626); }
            .pulse-slow { animation: pulse 3s infinite; }
        </style>
    </head>
    <body class="bg-gradient-to-br from-gray-900 via-purple-900 to-black text-white min-h-screen">
        <div class="container mx-auto px-4 py-12 max-w-7xl">
            
            <!-- العنوان -->
            <div class="text-center mb-16">
                <h1 class="text-6xl font-black bg-gradient-to-r from-yellow-400 via-orange-400 to-red-500 bg-clip-text text-transparent mb-6">
                    🤖 TradingView Strategy
                </h1>
                <p class="text-2xl text-yellow-300 font-semibold">استراتيجيتك الخاصة | تحديد الأزواج | إدارة المخاطر</p>
            </div>

            <!-- البطاقات الرئيسية -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-12">
                <!-- الرصيد والإحصائيات -->
                <div class="bg-gradient-to-br from-indigo-900/80 to-purple-900/80 backdrop-blur-xl p-10 rounded-3xl shadow-2xl border border-white/10">
                    <h3 class="text-2xl font-bold mb-8 text-center">💰 حالة الحساب</h3>
                    <div class="grid grid-cols-2 gap-8 text-center">
                        <div>
                            <p class="text-gray-300 mb-4">الرصيد الحالي</p>
                            <p id="current-balance" class="text-5xl font-black text-white">$10,000</p>
                            <p id="pnl-percent" class="text-3xl font-bold mt-4 pulse-slow">+0.00%</p>
                        </div>
                        <div>
                            <p class="text-gray-300 mb-4">الربح/الخسارة</p>
                            <p id="pnl-amount" class="text-5xl font-black text-green-400">$0</p>
                            <p id="daily-trades" class="text-xl text-gray-300 mt-4">الصفقات اليومية: 0/5</p>
                        </div>
                    </div>
                </div>

                <!-- إعدادات الأزواج -->
                <div class="bg-gradient-to-br from-emerald-900/80 to-teal-900/80 backdrop-blur-xl p-10 rounded-3xl shadow-2xl border border-white/10">
                    <h3 class="text-2xl font-bold mb-8 text-center">⚙️ إعدادات استراتيجيتك</h3>
                    <div class="space-y-6">
                        <div>
                            <label class="block text-lg font-semibold mb-3">أزواج TradingView الخاصة بك:</label>
                            <div id="user-pairs-display" class="grid grid-cols-3 gap-2 mb-4">
                                <span class="bg-yellow-500/20 text-yellow-300 px-4 py-2 rounded-xl font-bold text-sm">لا توجد أزواج</span>
                            </div>
                            <button onclick="openPairsModal()" 
                                    class="w-full bg-gradient-to-r from-yellow-500 to-orange-500 hover:from-yellow-600 hover:to-orange-600 
                                           text-white py-3 px-6 rounded-2xl font-bold text-lg shadow-xl hover:shadow-2xl transition-all">
                                📊 تحديد الأزواج
                            </button>
                        </div>
                        <div class="grid grid-cols-2 gap-4 text-center">
                            <div class="bg-black/30 p-4 rounded-xl">
                                <p class="text-sm text-gray-400">مخاطرة كل صفقة</p>
                                <p id="risk-display" class="text-2xl font-bold text-emerald-400">2%</p>
                            </div>
                            <div class="bg-black/30 p-4 rounded-xl">
                                <p class="text-sm text-gray-400">حجم الصفقة التالية</p>
                                <p id="position-size" class="text-2xl font-bold text-blue-400">$200</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- منطقة التحكم -->
            <div class="bg-gradient-to-r from-gray-800/50 to-black/50 backdrop-blur-xl p-10 rounded-3xl shadow-2xl mb-12 border border-white/20">
                <h3 class="text-3xl font-bold mb-10 text-center text-yellow-300">🎯 منطقة التنفيذ</h3>
                <div class="max-w-4xl mx-auto">
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                        <select id="pair-select" class="bg-gray-800/50 backdrop-blur-xl border border-white/30 px-6 py-4 rounded-2xl text-xl font-bold text-white">
                            <option>اختر زوجاً من استراتيجيتك</option>
                        </select>
                        <select id="direction-select" class="bg-gray-800/50 backdrop-blur-xl border border-white/30 px-6 py-4 rounded-2xl text-xl font-bold text-white">
                            <option>CALL</option>
                            <option>PUT</option>
                        </select>
                        <button onclick="executeStrategyTrade()" 
                                class="bg-gradient-to-r from-emerald-500 to-green-600 hover:from-emerald-600 hover:to-green-700 
                                       text-white px-12 py-4 rounded-2xl font-black text-2xl shadow-2xl hover:shadow-3xl transition-all col-span-1 md:col-span-1">
                            🚀 نفّذ إشارة TradingView
                        </button>
                    </div>
                </div>
            </div>

            <!-- سجل الصفقات -->
            <div class="bg-gradient-to-r from-gray-800/50 to-black/50 backdrop-blur-xl p-10 rounded-3xl shadow-2xl border border-white/20">
                <h3 class="text-3xl font-bold mb-10 text-center">📊 سجل الصفقات الأخيرة</h3>
                <div class="overflow-x-auto">
                    <table class="w-full text-right">
                        <thead>
                            <tr class="border-b-4 border-yellow-500/30">
                                <th class="p-6 font-black text-2xl text-yellow-400">الوقت</th>
                                <th class="p-6 font-black text-2xl text-yellow-400">الزوج</th>
                                <th class="p-6 font-black text-2xl text-yellow-400">الاتجاه</th>
                                <th class="p-6 font-black text-2xl text-yellow-400">الحجم</th>
                                <th class="p-6 font-black text-2xl text-yellow-400">النتيجة</th>
                                <th class="p-6 font-black text-2xl text-yellow-400">الرصيد</th>
                            </tr>
                        </thead>
                        <tbody id="trades-table">
                            <tr><td colspan="6" class="p-12 text-center text-gray-400 text-2xl">انتظر إشارة TradingView...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <!-- نافذة تحديد الأزواج -->
        <div id="pairs-modal" class="hidden fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div class="bg-gradient-to-br from-gray-900 to-black max-w-2xl w-full max-h-[90vh] overflow-y-auto rounded-3xl shadow-2xl border border-white/20">
                <div class="p-8 border-b border-white/10">
                    <h2 class="text-3xl font-black text-center mb-4 text-yellow-400">📊 تحديد أزواج استراتيجيتك</h2>
                    <p class="text-xl text-gray-300 text-center">اختر الأزواج من TradingView</p>
                </div>
                <div class="p-8">
                    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-8">
                        <label class="flex items-center space-x-3 space-x-reverse">
                            <input type="checkbox" value="EUR/USD" class="w-6 h-6 accent-yellow-500 rounded">
                            <span class="text-xl font-bold">EUR/USD</span>
                        </label>
                        <label class="flex items-center space-x-3 space-x-reverse">
                            <input type="checkbox" value="GBP/USD" class="w-6 h-6 accent-yellow-500 rounded">
                            <span class="text-xl font-bold">GBP/USD</span>
                        </label>
                        <label class="flex items-center space-x-3 space-x-reverse">
                            <input type="checkbox" value="USD/JPY" class="w-6 h-6 accent-yellow-500 rounded">
                            <span class="text-xl font-bold">USD/JPY</span>
                        </label>
                        <label class="flex items-center space-x-3 space-x-reverse">
                            <input type="checkbox" value="AUD/USD" class="w-6 h-6 accent-yellow-500 rounded">
                            <span class="text-xl font-bold">AUD/USD</span>
                        </label>
                        <label class="flex items-center space-x-3 space-x-reverse">
                            <input type="checkbox" value="USD/CAD" class="w-6 h-6 accent-yellow-500 rounded">
                            <span class="text-xl font-bold">USD/CAD</span>
                        </label>
                        <label class="flex items-center space-x-3 space-x-reverse">
                            <input type="checkbox" value="NZD/USD" class="w-6 h-6 accent-yellow-500 rounded">
                            <span class="text-xl font-bold">NZD/USD</span>
                        </label>
                        <label class="flex items-center space-x-3 space-x-reverse">
                            <input type="checkbox" value="EUR/GBP" class="w-6 h-6 accent-yellow-500 rounded">
                            <span class="text-xl font-bold">EUR/GBP</span>
                        </label>
                        <label class="flex items-center space-x-3 space-x-reverse">
                            <input type="checkbox" value="EUR/JPY" class="w-6 h-6 accent-yellow-500 rounded">
                            <span class="text-xl font-bold">EUR/JPY</span>
                        </label>
                    </div>
                    <div class="flex gap-4 justify-center">
                        <button onclick="savePairs()" 
                                class="bg-gradient-to-r from-emerald-500 to-green-600 hover:from-emerald-600 hover:to-green-700 
                                       text-white px-12 py-4 rounded-2xl font-bold text-xl shadow-2xl">
                            💾 حفظ الاستراتيجية
                        </button>
                        <button onclick="closePairsModal()" 
                                class="bg-gradient-to-r from-gray-600 to-gray-700 hover:from-gray-700 hover:to-gray-800 
                                       text-white px-12 py-4 rounded-2xl font-bold text-xl shadow-xl">
                            ❌ إلغاء
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <script>
            let selectedPairs = [];
            let refreshInterval;

            async function updateDashboard() {
                try {
                    const res = await fetch('/api/dashboard');
                    const data = await res.json();
                    
                    // تحديث الرصيد
                    document.getElementById('current-balance').textContent = `$${data.balance.toLocaleString()}`;
                    const pnlPercent = data.pnl_percent;
                    const pnlEl = document.getElementById('pnl-percent');
                    pnlEl.textContent = `${pnlPercent >= 0 ? '+' : ''}${pnlPercent.toFixed(2)}%`;
                    pnlEl.className = `text-3xl font-bold mt-4 ${pnlPercent >= 0 ? 'text-green-400' : 'text-red-400'} pulse-slow`;
                    
                    document.getElementById('pnl-amount').textContent = `$${data.pnl.toLocaleString()}`;
                    document.getElementById('pnl-amount').className = `text-5xl font-black ${data.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`;
                    document.getElementById('daily-trades').textContent = `الصفقات اليومية: ${data.daily_trades}/${data.max_daily_trades}`;
                    
                    // تحديث حجم الصفقة التالية
                    document.getElementById('position-size').textContent = `$${(data.balance * 0.02).toLocaleString()}`;
                    
                    // تحديث قائمة الأزواج
                    document.getElementById('pair-select').innerHTML = '<option>اختر زوجاً من استراتيجيتك</option>' + 
                        selectedPairs.map(pair => `<option value="${pair}">${pair}</option>`).join('');
                    
                    // تحديث الجدول
                    updateTradesTable(data.recent_trades);
                    
                } catch (error) {
                    console.error('خطأ:', error);
                }
            }

            function updateTradesTable(trades) {
                const tbody = document.getElementById('trades-table');
                if (trades.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="p-12 text-center text-gray-400 text-2xl">انتظر إشارة TradingView...</td></tr>';
                    return;
                }
                tbody.innerHTML = trades.slice(-15).map(trade => `
                    <tr class="hover:bg-white/10 transition-all border-b border-white/10">
                        <td class="p-6 font-mono text-lg">${trade.time}</td>
                        <td class="p-6 font-black text-2xl">${trade.pair}</td>
                        <td class="p-6">
                            <span class="px-6 py-3 rounded-2xl font-bold text-xl
                                ${trade.direction === 'CALL' ? 'bg-green-500/30 text-green-400 border-2 border-green-500/50' : 'bg-red-500/30 text-red-400 border-2 border-red-500/50'}">
                                ${trade.direction}
                            </span>
                        </td>
                        <td class="p-6 font-bold text-emerald-400 text-2xl">$${trade.amount.toLocaleString()}</td>
                        <td class="p-6">
                            <span class="px-8 py-4 rounded-3xl font-black text-2xl shadow-2xl
                                ${trade.result.includes('✅') ? 'trade-win text-white' : 'trade-loss text-white'}">
                                ${trade.result}
                            </span>
                        </td>
                        <td class="p-6 font-bold text-blue-400 text-2xl">$${trade.balance_after.toLocaleString()}</td>
                    </tr>
                `).join('');
            }

            async function executeStrategyTrade() {
                const pair = document.getElementById('pair-select').value;
                const direction = document.getElementById('direction-select').value;
                
                if (!pair || pair === 'اختر زوجاً من استراتيجيتك') {
                    alert('⚠️ اختر زوجاً من استراتيجيتك أولاً!');
                    return;
                }
                
                const res = await fetch('/api/trade/execute', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({pair, direction, signal: 'TradingView Strategy'})
                });
                const result = await res.json();
                
                if (result.success) {
                    alert(`✅ تم تنفيذ إشارة TradingView!\n${result.result}`);
                } else {
                    alert(`❌ خطأ: ${result.message}`);
                }
                updateDashboard();
            }

            function openPairsModal() {
                document.getElementById('pairs-modal').classList.remove('hidden');
            }

            function closePairsModal() {
                document.getElementById('pairs-modal').classList.add('hidden');
            }

            async function savePairs() {
                const checkboxes = document.querySelectorAll('#pairs-modal input[type="checkbox"]:checked');
                selectedPairs = Array.from(checkboxes).map(cb => cb.value);
                
                if (selectedPairs.length === 0) {
                    alert('⚠️ اختر على الأقل زوج واحد!');
                    return;
                }
                
                await fetch('/api/strategy/pairs', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({pairs: selectedPairs})
                });
                
                document.getElementById('user-pairs-display').innerHTML = selectedPairs.map(pair => 
                    `<span class="bg-emerald-500/30 text-emerald-400 px-6 py-3 rounded-2xl font-bold text-lg border-2 border-emerald-500/50">${pair}</span>`
                ).join('');
                
                closePairsModal();
                updateDashboard();
            }

            // بدء التحديث
            refreshInterval = setInterval(updateDashboard, 3000);
            updateDashboard();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# APIs الاحترافية
@app.get("/api/dashboard")
async def get_dashboard():
    bot.reset_daily_counter()
    total_trades = len(bot.trades)
    wins = sum(1 for trade in bot.trades if "✅" in trade.result)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    return {
        "balance": round(bot.balance, 2),
        "pnl": round(bot.balance - bot.initial_balance, 2),
        "pnl_percent": round(((bot.balance - bot.initial_balance) / bot.initial_balance) * 100, 2),
        "total_trades": total_trades,
        "win_rate": f"{win_rate:.1f}%",
        "daily_trades": bot.daily_trades,
        "max_daily_trades": bot.max_daily_trades,
        "user_pairs": bot.user_pairs,
        "recent_trades": list(bot.trades)
    }

@app.post("/api/strategy/pairs")
async def set_strategy_pairs(request: Dict):
    pairs = request.get("pairs", [])
    bot.set_user_pairs(pairs)
    return {"success": True, "pairs": bot.user_pairs, "count": len(bot.user_pairs)}

@app.post("/api/trade/execute")
async def execute_trade(request: Dict):
    pair = request.get("pair", "")
    direction = request.get("direction", "CALL")
    signal = request.get("signal", "Manual")
    return bot.execute_trade(pair, direction, signal)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
