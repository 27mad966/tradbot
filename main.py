import os
import json
import asyncio
import ccxt
from datetime import datetime
from collections import deque
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="🤖 Sovereign Bot v3.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

class TradingBot:
    def __init__(self):
        # التأكد من سحب المتغيرات من ريندر
        self.api_key = os.getenv("BINANCE_API_KEY", "").strip()
        self.secret_key = os.getenv("BINANCE_SECRET_KEY", "").strip()
        
        self.exchange = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.secret_key,
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True, # مزامنة الوقت مع بايننس
                'recvWindow': 60000, 
                'defaultType': 'spot'
            }
        })
        
        # روابط التست نت الثابتة
        self.exchange.urls['api']['public'] = 'https://testnet.binance.vision/api'
        self.exchange.urls['api']['private'] = 'https://testnet.binance.vision/api'
        
        self.trades = deque(maxlen=50)
        self.balance = 0.0
        self.active_symbol = "USDT"

    async def update_balance(self):
        try:
            if not self.api_key:
                self.balance = -1
                return
            
            # مزامنة وقت السيرفر قبل جلب الرصيد
            self.exchange.load_markets() 
            bal = self.exchange.fetch_balance()
            
            active = {k: v['total'] for k, v in bal['total'].items() if v > 0}
            if active:
                self.active_symbol = list(active.keys())[0]
                self.balance = active[self.active_symbol]
            else:
                self.balance = 0.0 # الحساب فارغ تماماً
        except Exception as e:
            print(f"❌ API Connection Error: {e}")
            self.balance = -2 # خطأ في الصلاحية أو المفاتيح

    def execute_trade(self, pair, direction):
        # تصحيح الزوج لضمان التوافق مع التست نت
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

# ... (باقي مسارات الـ FastAPI والـ HTML كما هي)
