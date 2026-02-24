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
client = None
try:
    client = Client(
        api_key=os.getenv('API_KEY'),
        api_secret=os.getenv('API_SECRET'),
        testnet=testnet
    )
except:
    logger.error("❌ فشل في تهيئة Binance Client")

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content="""
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
        .error { background: #ff4444; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Trading Bot Dashboard</h1>
        <div class="status live">✅ LIVE - Webhook Active</div>
        <div class="status testnet">🔗 BINANCE TESTNET: """ + ("متصل" if client else "❌ غير متصل") + """</div>
        <div id="balance">جاري التحميل...</div>
        <div id="status">جاري التحقق...</div>
    </div>
    <script>
        setInterval(async () => {
            try {
                const res = await fetch('/api/balance');
                const data = await res.json();
                document.getElementById('balance').innerHTML = 
                    `💰 USDT: $${data.total || 0} | P&L: $${data.pnl || 0}`;
                document.getElementById('status').innerHTML = data.status;
            } catch(e) {
                document.getElementById('balance').innerHTML = '❌ خطأ في الاتصال';
            }
        }, 3000);
    </script>
</body>
</html>""")

@app.get("/api/balance")
async def get_balance():
    if not client:
        return {"total": 0, "pnl": 0, "status": "❌ Binance غير متصل"}
    
    try:
        account = client.futures_account()
        return {
            "total": float(account['totalWalletBalance']),
            "pnl": float(account['totalUnrealizedProfit']),
            "status": "✅ Testnet متصل"
        }
    except Exception as e:
        return {"total": 0, "pnl": 0, "status": f"❌ خطأ: {str(e)[:50]}"}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        form = await request.form()
        
        # التحقق من البيانات مع الحماية من None
        symbol = form.get('symbol')
        action = form.get('action')
        price_str = form.get('price')
        
        if not all([symbol, action, price_str]):
            return {"status": "error", "message": "❌ بيانات ناقصة"}
        
        symbol = symbol.strip().upper()
        action = action.strip().lower()
        price = float(price_str.strip())
        
        logger.info(f"🔔 {symbol} {action} ${price}")
        
        if not client:
            return {"status": "error", "message": "❌ Binance Client غير متصل"}
        
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
                    return {"status": "success", "message": f"🧪 TP: {symbol} مغلق (ID: {order['orderId']})"}
            return {"status": "no_position", "message": f"لا يوجد مركز مفتوح لـ {symbol}"}
            
    except Exception as e:
        logger.error(f"❌ خطأ في webhook: {str(e)}")
        return {"status": "error", "message": f"خطأ: {str(e)[:100]}"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
