from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from binance.client import Client
from binance.enums import *
import os
import json
from datetime import datetime

app = FastAPI()

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

TESTNET = os.getenv('TESTNET', 'true').lower() == 'true'
client = Client(api_key=os.getenv('API_KEY'), api_secret=os.getenv('API_SECRET'), testnet=TESTNET)

async def get_balance():
    try:
        balance = client.get_account()
        usdt_balance = 0
        for asset in balance['balances']:
            if asset['asset'] == 'USDT':
                usdt_balance = float(asset['free'])
        return {"usdt": usdt_balance, "testnet": TESTNET}
    except:
        return {"usdt": 0, "testnet": TESTNET}

@app.post("/webhook")  # ← الجديد لـ TradingView
async def webhook(request: Request):
    try:
        data = await request.json()
        print(f"Webhook data: {data}")  # Log
        
        if "buy" in str(data).lower() or "long" in str(data).lower():
            return await buy_webhook(request)
        if "sell" in str(data).lower() or "short" in str(data).lower():
            return await sell_webhook(request)
        return {"status": "Webhook OK", "data": data}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/buy")
async def buy_webhook(request: Request):
    try:
        data = await request.json()
        symbol = data.get('symbol', 'ETHUSDT')
        amount = float(data.get('amount', 10))
        
        order = client.create_order(symbol=symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET, quoteOrderQty=amount)
        current_price = float(order['fills'][0]['price'])
        trade = {
            "id": len(load_trades()) + 1, "type": "BUY", "symbol": symbol,
            "amount": amount / current_price, "price": current_price, "total_usdt": amount,
            "timestamp": datetime.now().isoformat(), "status": "OPEN"
        }
        save_trade(trade)
        return {"status": "BUY OK", "trade": trade}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/sell")
async def sell_webhook(request: Request):
    try:
        data = await request.json()
        symbol = data.get('symbol', 'ETHUSDT')
        amount = float(data.get('amount', 0.01))
        
        order = client.create_order(symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=amount)
        current_price = float(order['fills'][0]['price'])
        trades = load_trades()
        open_trades = [t for t in trades if t["status"] == "OPEN" and t["symbol"] == symbol]
        
        if open_trades:
            buy_trade = open_trades[0]
            profit = (current_price - buy_trade["price"]) * amount
            buy_trade.update({
                "status": "CLOSED", "sell_price": current_price,
                "sell_amount": amount, "profit": profit,
                "sell_timestamp": datetime.now().isoformat()
            })
            save_trade(buy_trade)
        
        return {"status": "SELL OK", "profit": profit if open_trades else 0}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/balance")
async def balance_api():
    return await get_balance()

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    balance = await get_balance()
    trades = load_trades()
    total_profit = sum(t.get("profit", 0) for t in trades if t.get("profit"))
    open_trades = len([t for t in trades if t["status"] == "OPEN"])
    closed_trades = len([t for t in trades if t["status"] == "CLOSED"])
    recent_trades = trades[-10:]
    
    # HTML Dashboard (نفس الكود السابق - مختصر)
    html_content = f"""
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="UTF-8"><title>Trading Dashboard</title>
<style>*{{margin:0;padding:0;box-sizing:border-box;}}body{{font-family:'Segoe UI';background:linear-gradient(135deg,#0f0f23 0%,#1a1a2e 100%);color:white;padding:20px;}}.container{{max-width:1200px;margin:0 auto;}}h1{{text-align:center;margin-bottom:30px;color:#00ff88;}}.status{{display:flex;gap:20px;margin-bottom:30px;}}.status-card{{flex:1;background:rgba(255,255,255,0.1);padding:20px;border-radius:15px;text-align:center;}}.profit{{color:#00ff88;font-size:2em;}}.loss{{color:#ff4444;}}.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;margin-bottom:30px;}}.stat{{background:rgba(255,255,255,0.1);padding:20px;border-radius:15px;text-align:center;}}table{{width:100%;border-collapse:collapse;background:rgba(255,255,255,0.1);border-radius:15px;overflow:hidden;}}th,td{{padding:15px;text-align:right;border-bottom:1px solid rgba(255,255,255,0.2);}}th{{background:rgba(0,255,136,0.2);}}tr.open{{background:rgba(0,255,0,0.1);}}tr.closed{{background:rgba(255,255,255,0.05);}}</style>
</head>
<body>
<div class="container">
<h1>🟢 Live Trading Dashboard</h1>
<div class="status">
<div class="status-card"> <h3>{'Testnet' if balance['testnet'] else 'Live'}</h3><div>🟢 {'متصل' if balance['usdt'] else 'خطأ'}</div></div>
<div class="status-card"><h3>USDT</h3><div>{balance['usdt']:.2f}</div></div>
</div>
<div class="stats">
<div class="stat"><h3>الربح الكلي</h3><span class="{'profit' if total_profit>=0 else 'loss'}">{total_profit:.2f} USDT</span></div>
<div class="stat"><h3>مفتوحة</h3><span>{open_trades}</span></div>
<div class="stat"><h3>مغلقة</h3><span>{closed_trades}</span></div>
</div>
<h2>📊 آخر الصفقات:</h2>
<table>
<tr><th>النوع</th><th>الزوج</th><th>السعر</th><th>الكمية</th><th>البيع</th><th>الربح</th><th>التاريخ</th></tr>
"""
    
    for t in recent_trades:
        html_content += f'''
<tr class="{"open" if t["status"]=="OPEN" else "closed"}">
<td>{t["type"]}</td><td>{t["symbol"]}</td><td>${t["price"]:.4f}</td><td>{t["amount"]:.4f}</td><td>${t.get("sell_price",0):.4f}</td><td class="{"profit" if t.get("profit",0)>0 else "loss"}">{t.get("profit","0"):.2f if t.get("profit") else "-"} USDT</td><td>{t["timestamp"][:16]}</td>
</tr>'''
    
    html_content += """
</table></div><script>setInterval(()=>location.reload(),5000);</script></body></html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
