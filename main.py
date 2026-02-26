"""
نظام تداول آلي مع API Web - متوافق مع Render.com
خالٍ من التبعيات المعقدة
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any
import uvicorn
import random
from datetime import datetime
import threading
import time
from collections import deque

app = FastAPI(title="🤖 Trading Bot API", version="2.1")

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

@app.get("/")
async def root():
    return {"message": "🤖 Trading Bot API تعمل بنجاح!", "status": "active"}

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

@app.get("/api/stats")
async def get_stats():
    total_trades = len(bot.trades)
    wins = sum(1 for trade in bot.trades if "✅" in trade.result)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": total_trades - wins,
        "win_rate": f"{win_rate:.1f}%",
        "balance": round(bot.balance, 2),
        "pnl": round(bot.balance - bot.initial_balance, 2),
        "pnl_percent": f"{((bot.balance - bot.initial_balance) / bot.initial_balance) * 100:.2f}%"
    }

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

@app.get("/api/status")
async def get_status():
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

@app.get("/api/dashboard")
async def get_dashboard():
    """بيانات لوحة التحكم الشاملة"""
    total_trades = len(bot.trades)
    wins = sum(1 for trade in bot.trades if "✅" in trade.result)
    
    return {
        "balance": round(bot.balance, 2),
        "pnl": round(bot.balance - bot.initial_balance, 2),
        "pnl_percent": round(((bot.balance - bot.initial_balance) / bot.initial_balance) * 100, 2),
        "total_trades": total_trades,
        "win_rate": f"{(wins/total_trades*100):.1f}%" if total_trades > 0 else "0%",
        "trading_status": bot.is_trading,
        "recent_trades": list(bot.trades)[-10:]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=10000)
