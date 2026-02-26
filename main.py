import os
import ccxt
import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from collections import deque
from datetime import datetime

app = FastAPI()

class TradingBot:
    def __init__(self):
        # القراءة بناءً على صورتك في ريندر (image_dd9710.png)
        self.api_key = os.getenv("API_SECRET", "").strip() 
        self.secret_key = os.getenv("Secret_Key", "").strip()
        
        self.exchange = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.secret_key,
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True, # حل مشكلة مزامنة الوقت
                'recvWindow': 60000, 
                'defaultType': 'spot'
            }
        })
        
        # الروابط الرسمية لشبكة التست نت (تتوافق مع صورتك رقم 3)
        self.exchange.urls['api']['public'] = 'https://testnet.binance.vision/api'
        self.exchange.urls['api']['private'] = 'https://testnet.binance.vision/api'
        
        self.trades = deque(maxlen=50)
        self.balance = 0.0

    async def update_balance(self):
        try:
            if not self.api_key or not self.secret_key:
                return
            
            # جلب الرصيد الكامل
            bal = self.exchange.fetch_balance()
            # البحث عن USDT أو أي عملة بها رصيد (BTC, BNB)
            usdt_bal = bal['total'].get('USDT', 0.0)
            
            if usdt_bal > 0:
                self.balance = usdt_bal
            else:
                # إذا لم يجد USDT، يبحث عن أول عملة بها رصيد
                for coin, total in bal['total'].items():
                    if total > 0:
                        self.balance = total
                        break
        except Exception as e:
            print(f"Connection Error: {e}")
