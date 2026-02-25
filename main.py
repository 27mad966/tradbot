from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from binance.client import Client
from binance.enums import *
import os
import json
from datetime import datetime

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ========== قاعدة بيانات الصفقات ==========
TRADES_FILE = "trades.json"

def load_trades():
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE, 'r') as f:
            return json.load(f)
    return []

def save_trade(trade_data):
    trades = load_trades()
    trades.append(trade_data)
    with open(TRADES_FILE, 'w') as f:
        json.dump(trades, f, indent=2)

# ========== Binance Client ==========
TESTNET = os.getenv('TESTNET', 'true').lower() == 'true'
client = Client(
    api_key=os.getenv('API_KEY'),
    api_secret=os.getenv('API_SECRET'),
    testnet=TESTNET
)

# ========== API Endpoints ==========
@app.get("/api/balance")
async def get_balance():
    try:
        balance = client.get_account()
        usdt_balance = 0
        btc_balance = 0
        
        for asset in balance['balances']:
            if asset['asset'] == 'USDT':
                usdt_balance = float(asset['free'])
            elif asset['asset'] == 'BTC':
                btc_balance = float(asset['free'])
        
        return {
            "usdt": usdt_balance,
            "btc": btc_balance,
            "testnet": TESTNET
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/buy")
async def buy_webhook(request: Request):
    try:
        data = await request.json()
        symbol = data.get('symbol', 'ETHUSDT')
        amount = float(data.get('amount', 10))
        
        # تنفيذ الشراء
        order = client.create_order(
            symbol=symbol,
            side=SIDE_BUY,
            type=ORDER_TYPE_MARKET,
            quoteOrderQty=amount  # مبلغ USDT
        )
        
        # حفظ صفقة الشراء
        current_price = float(order['fills'][0]['price'])
        trade = {
            "id": len(load_trades()) + 1,
            "type": "BUY",
            "symbol": symbol,
            "amount": amount / current_price,  # كمية العملة
            "price": current_price,
            "total_usdt": amount,
            "timestamp": datetime.now().isoformat(),
            "status": "OPEN"
        }
        save_trade(trade)
        
        return {"status": "BUY executed", "trade": trade}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/sell")
async def sell_webhook(request: Request):
    try:
        data = await request.json()
        symbol = data.get('symbol', 'ETHUSDT')
        amount = float(data.get('amount', 0.01))
        
        # تنفيذ البيع
        order = client.create_order(
            symbol=symbol,
            side=SIDE_SELL,
            type=ORDER_TYPE_MARKET,
            quantity=amount
        )
        
        # حساب الربح/الخسارة
        current_price = float(order['fills'][0]['price'])
        trades = load_trades()
        open_trades = [t for t in trades if t["status"] == "OPEN" and t["symbol"] == symbol]
        
        if open_trades:
            buy_trade = open_trades[0]
            profit = (current_price - buy_trade["price"]) * amount
            buy_trade["status"] = "CLOSED"
            buy_trade["sell_price"] = current_price
            buy_trade["sell_amount"] = amount
            buy_trade["profit"] = profit
            buy_trade["sell_timestamp"] = datetime.now().isoformat()
            save_trade(buy_trade)  # حفظ التعديل
        
        return {"status": "SELL executed", "profit": profit}
    except Exception as e:
        return {"error": str(e)}

# ========== Dashboard ==========
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    try:
        balance = await get_balance()
        
        trades = load_trades()
        total_profit = sum(t.get("profit", 0) for t in trades if t.get("profit"))
        open_trades = len([t for t in trades if t["status"] == "OPEN"])
        closed_trades = len([t for t in trades if t["status"] == "CLOSED"])
        recent_trades = trades[-10:]  # آخر 10 صفقات
        
        return templates.TemplateResponse("index.html", {
            "request": request,
            "balance": balance,
            "total_profit": total_profit,
            "open_trades": open_trades,
            "closed_trades": closed_trades,
            "recent_trades": recent_trades
        })
    except:
        return templates.TemplateResponse("index.html", {
            "request": request,
            "balance": {"error": "API Error"},
            "total_profit": 0,
            "open_trades": 0,
            "closed_trades": 0,
            "recent_trades": []
        })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
