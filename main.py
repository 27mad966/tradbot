import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from binance.client import Client
from binance.exceptions import BinanceAPIException
import uvicorn

app = FastAPI(title="Trading Bot - Binance Testnet")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Binance Testnet Client
testnet = os.getenv('TESTNET', 'false').lower() == 'true'
client = Client(
    api_key=os.getenv('API_KEY'),
    api_secret=os.getenv('API_SECRET'),
    testnet=testnet
)

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>Trading Bot Dashboard</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body { font-family: Arial; margin: 40px; background: #1a1a2e; color: #fff; }
        .container { max-width: 800px; margin: 0 auto; }
        .status { padding: 20px; border-radius: 10px; margin: 20px 0; }
        .live { background: #00ff88; color: #000; }
        .testnet { background: #ffaa00; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Trading Bot Dashboard</h1>
        <div class="status live">✅ LIVE - Webhook Active</div>
        <div class="status testnet">🔗 BINANCE TESTNET CONNECTED</div>
        <div id="balance">Loading...</div>
    </div>
    <script>
        setInterval(async () => {
            try {
                const res = await fetch('/api/balance');
                const data = await res.json();
                document.getElementById('balance').innerHTML = 
                    `💰 USDT: $${data.total} | P&L: $${data.pnl}`;
            } catch(e) {}
        }, 5000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html)

@app.get("/api/balance")
async def get_balance():
    try:
        account = client.futures_account()
        return {
            "total": float(account['totalWalletBalance']),
            "pnl": float(account['totalUnrealizedProfit'])
        }
    except:
        return {"total": 0, "pnl": 0}

@app.post("/webhook")
async def webhook(request: Request):
    form = await request.form()
    symbol = form.get('symbol').upper()
    action = form.get('action').lower()
    price = float(form.get('price'))
    
    logger.info(f"🔔 {symbol} {action} ${price}")
    
    try:
        if action in ['buy', 'sell']:
            quantity = round((10 / price) * 0.98, 3)
            order = client.futures_create_order(
                symbol=symbol,
                side=action.upper(),
                type="MARKET",
                quantity=quantity
            )
            result = f"✅ TESTNET {action.upper()}: {symbol} @ ${price:.2f} (ID: {order['orderId']})"
            logger.info(result)
            return {"status": "success", "message": result}
        elif action == 'tp':
            positions = client.futures_position_information(symbol=symbol)
            for pos in positions:
                if float(pos['positionAmt']) != 0:
                    side = "SELL" if float(pos['positionAmt']) > 0 else "BUY"
                    qty = abs(float(pos['positionAmt']))
                    order = client.futures_create_order(
                        symbol=symbol,
                        side=side,
                        type="MARKET",
                        quantity=round(qty, 3)
                    )
                    return {"status": "success", "message": f"🧪 TP: {symbol} CLOSED (ID: {order['orderId']})"}
            return {"status": "no_position", "message": f"لا يوجد مركز مفتوح لـ {symbol}"}
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
