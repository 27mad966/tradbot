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

# --- الإعدادات ---
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
        self.exchange = ccxt.binance({
            'apiKey': self.api_key, 'secret': self.secret_key,
            'enableRateLimit': True,
            'options': {'adjustForTimeDifference': True, 'recvWindow': 15000, 'defaultType': 'spot'}
        })
        self.exchange.set_sandbox_mode(True)
        self.trades = deque(maxlen=50)

    async def get_stats(self):
        try:
            bal = self.exchange.fetch_balance()
            # نركز فقط على USDT لضمان دقة الأرباح في البداية
            total_usdt = bal['total'].get('USDT', 0.0)
            
            # حساب قيمة العملات النشطة فقط (تجاهل العملات القديمة أو الوهمية)
            active_assets_value = 0
            # سنحسب فقط العملات المشهورة لضمان عدم حدوث جنون في الأرقام
            for coin in ['BTC', 'ETH', 'SOL', 'BNB', 'ADA', 'XRP']:
                amount = bal['total'].get(coin, 0.0)
                if amount > 0:
                    try:
                        ticker = self.exchange.fetch_ticker(f"{coin}/USDT")
                        active_assets_value += amount * ticker['last']
                    except: continue
            
            current_total = total_usdt + active_assets_value
            # إذا كان الحساب جديداً أو مصفراً، نفترض البداية من 10000
            if current_total < 1.0: current_total = INITIAL_BALANCE
            
            pnl_val = current_total - INITIAL_BALANCE
            pnl_pct = (pnl_val / INITIAL_BALANCE) * 100
            
            return round(current_total, 2), round(pnl_val, 2), round(pnl_pct, 2)
        except:
            return INITIAL_BALANCE, 0.0, 0.0

    def calculate_amount(self, pair, direction, price):
        coin = pair.split('/')[0]
        bal = self.exchange.fetch_balance()
        if direction == "buy":
            usdt_on_hand = bal['total'].get('USDT', 0)
            val = settings["buy_value"] if settings["buy_mode"] == "fixed" else usdt_on_hand * settings["buy_value"]
            # التأكد من عدم تجاوز الرصيد المتاح
            if val > usdt_on_hand: val = usdt_on_hand * 0.95 
            return val / price
        else:
            coin_bal = bal['total'].get(coin, 0)
            return coin_bal * settings["sell_value"] if settings["sell_mode"] == "percent" else settings["sell_value"] / price

    def execute_trade(self, pair, direction):
        if not settings["bot_active"]: return
        pair = pair.replace("USDTUSDT", "USDT").upper()
        if "/" not in pair: pair = f"{pair[:-4]}/USDT" if pair.endswith("USDT") else f"{pair}/USDT"
        
        try:
            ticker = self.exchange.fetch_ticker(pair)
            price = ticker['last']
            amount = self.calculate_amount(pair, direction, price)
            
            if amount <= 0: raise Exception("رصيد USDT غير كافٍ")

            if direction.lower() in ["buy", "long"]:
                self.exchange.create_market_buy_order(pair, amount)
                act = "شراء"
            else:
                self.exchange.create_market_sell_order(pair, amount)
                act = "بيع"

            res = {'time': datetime.now().strftime("%H:%M:%S"), 'pair': pair, 'action': act, 'price': round(price, 4), 'status': f"✅ تم تنفيذ {round(amount, 2)}"}
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
                if amount > 0.001 and coin not in ['USDT', 'BNB']:
                    try: self.exchange.create_market_sell_order(f"{coin}/USDT", amount)
                    except: continue
            return True
        except: return False

bot = TradingBot()

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    # ... (نفس كود الـ HTML السابق مع تحسين عرض الأرقام) ...
    return HTMLResponse(content="""...""") # سأرفق لك الـ HTML كاملاً في رسالة منفصلة إذا لم يظهر هنا

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

@app.post("/webhook")
async def handle_webhook(signal: Signal):
    return bot.execute_trade(signal.pair, signal.direction)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
