"""
نظام تداول آلي مع API Web للنشر على Render.com
متوافق مع بيئة الإنتاج بدون GUI
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import uvicorn
import asyncio
import random
from datetime import datetime
import threading
import time
from collections import deque

app = FastAPI(title="🤖 Trading Bot API", version="2.0")

# إعداد CORS للواجهة الأمامية
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
        self.trades: deque = deque(maxlen=100)  # آخر 100 صفقة
        self.is_trading = False
        self.lock = asyncio.Lock()
    
    async def execute_trade(self, pair: str, direction: str, amount: float) -> Dict[str, Any]:
        """تنفيذ صفقة تداول"""
        async with self.lock:
            if amount > self.balance:
                return {"success": False, "message": "الرصيد غير كافي"}
            
            # محاكاة نتيجة التداول
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

# إنشاء البوت
bot = TradingBot()

@app.get("/")
async def root():
    return {"message": "🤖 Trading Bot API تعمل بنجاح!", "status": "active"}

@app.get("/api/balance")
async def get_balance():
    """جلب الرصيد الحالي"""
    return {
        "balance": bot.balance,
        "initial_balance": bot.initial_balance,
        "pnl": bot.balance - bot.initial_balance,
        "pnl_percent": ((bot.balance - bot.initial_balance) / bot.initial_balance) * 100
    }

@app.get("/api/trades")
async def get_trades():
    """جلب سجل الصفقات"""
    return list(bot.trades)

@app.post("/api/trade/manual")
async def manual_trade(pair: str, direction: str, amount: float):
    """تنفيذ صفقة يدوية"""
    result = await bot.execute_trade(pair, direction, amount)
    return result

@app.get("/api/trade/start")
async def start_trading():
    """بدء التداول التلقائي"""
    if not bot.is_trading:
        bot.is_trading = True
        # تشغيل التداول في خيط منفصل
        threading.Thread(target=auto_trading_loop, daemon=True).start()
        return {"status": "started", "message": "✅ بدأ التداول التلقائي"}
    return {"status": "already_running", "message": "⏹️ التداول يعمل بالفعل"}

@app.get("/api/trade/stop")
async def stop_trading():
    """إيقاف التداول التلقائي"""
    bot.is_trading = False
    return {"status": "stopped", "message": "⏹️ توقف التداول التلقائي"}

@app.get("/api/stats")
async def get_stats():
    """إحصائيات شاملة"""
    total_trades = len(bot.trades)
    wins = sum(1 for trade in bot.trades if "✅" in trade.result)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    return {
        "total_trades": total_trades,
        "wins": wins,
        "win_rate": f"{win_rate:.1f}%",
        "balance": bot.balance,
        "pnl": bot.balance - bot.initial_balance,
        "pnl_percent": f"{((bot.balance - bot.initial_balance) / bot.initial_balance) * 100:.2f}%"
    }

def auto_trading_loop():
    """حلقة التداول التلقائي"""
    pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "ETH/USD"]
    directions = ["CALL", "PUT"]
    
    while bot.is_trading:
        try:
            pair = random.choice(pairs)
            direction = random.choice(directions)
            amount = random.uniform(25, 100)
            
            # تنفيذ الصفقة بشكل متزامن في الخيط الرئيși
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(bot.execute_trade(pair, direction, amount))
            loop.close()
            
            time.sleep(5)  # انتظار 5 ثواني
        except Exception as e:
            print(f"خطأ في التداول التلقائي: {e}")
            time.sleep(1)

@app.get("/api/status")
async def get_status():
    """حالة النظام"""
    total_trades = len(bot.trades)
    wins = sum(1 for trade in bot.trades if "✅" in trade.result)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    return {
        "trading_status": "🟢 يعمل" if bot.is_trading else "🔴 متوقف",
        "balance": f"${bot.balance:.2f}",
        "total_trades": total_trades,
        "win_rate": f"{win_rate:.1f}%",
        "recent_trades": len(bot.trades)
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=10000,
        reload=False,
        log_level="info"
    )
