from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import json
import os
import hmac
import hashlib
import time
import requests
from datetime import datetime

app = FastAPI(title="🚀 Trading Bot Pro v8.1 - Binance Testnet")

# ===== ضع Keys هنا بالضبط =====
BINANCE_API_KEY = "OiPl7xWT2zOuZMu2for53DDmJvludenpCiIOghBW4KKfQksOwCOHZmVCUsGeQCI3"  # من الصورة
BINANCE_SECRET_KEY = "D83WGpMFTUOl38r6VdeUlEJfVx32YHIVSFFCGp4qXnMOZMuNyV0WScZH2gP09BeI"  # من الصورة

TRADES_FILE = "trades.json"

def binance_request(method, endpoint, params=None):
    timestamp = int(time.time() * 1000)
    params = params or {}
    params['timestamp'] = timestamp
    query = '&'.join(f"{k}={v}" for k, v in params.items())
    signature = hmac.new(BINANCE_SECRET_KEY.encode(), query.encode(), hashlib.sha256).hexdigest()
    params['signature'] = signature
    
    url = "https://testnet.binance.vision/api" + endpoint
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    
    response = requests.request(method, url, headers=headers, params=params)
    data = response.json()
    
    if 'code' in data and data['code'] != 200:
        return {'error': data.get('msg', 'API Error')}
    return data

def get_account():
    return binance_request('GET', '/v3/account')

def new_order(symbol, side, quantity):
    params = {
        'symbol': symbol,
        'side': side,
        'type': 'MARKET',
        'quantity': f"{quantity:.3f}"
    }
    return binance_request('POST', '/v3/order', params)

def load_trades():
    try:
        if os.path.exists(TRADES_FILE):
            with open(TRADES_FILE) as f:
                return json.load(f)[-15:]
    except:
        pass
    return []

def save_trade(trade):
    trades = load_trades()
    trades.append(trade)
    try:
        with open(TRADES_FILE, 'w') as f:
            json.dump(trades, f)
    except:
        pass

@app.get("/api/account")
async def api_account():
    account = get_account()
    balances = {}
    for b in account.get('balances', []):
        amt = float(b['free'])
        if amt > 0.001:
            balances[b['asset']] = amt
    return {"balances": balances, "status": "ok"}

@app.get("/api/trades")
async def api_trades():
    return {"trades": load_trades(), "count": len(load_trades())}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        symbol = data.get("symbol", "BTCUSDT")
        action = data.get("action", "BUY")
        price = data.get("price", 95000)
        amount_usdt = data.get("amount", 10)
        
        side = "BUY" if "BUY" in action.upper() else "SELL"
        quantity = amount_usdt / price
        
        order = new_order(symbol, side, quantity)
        
        trade = {
            "time": datetime.now().isoformat(),
            "symbol": symbol,
            "action": action,
            "side": side,
            "price": price,
            "amount": amount_usdt,
            "quantity": quantity,
            "orderId": order.get('orderId'),
            "status": order.get('status')
        }
        
        save_trade(trade)
        return {"status": "EXECUTED", "order": order, "trade": trade}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}

@app.get("/ping")
async def ping():
    return {"status": "ready", "binance": "testnet"}

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>
<html dir="rtl">
<head>
<meta charset="UTF-8">
<title>🚀 Binance Testnet Trading Bot</title>
<meta name="viewport"
