import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from binance.client import Client
from binance.exceptions import BinanceAPIException
import uvicorn

# إعدادات الـ Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Trading Bot - Binance Testnet")

# تهيئة عميل Binance Testnet
testnet = os.getenv('TESTNET', 'false').lower() == 'true'
BINANCE_BASE_URL = "https://testnet.binance.vision" if testnet else "https://api.binance.com"

client = Client(
    api_key=os.getenv('API_KEY', ''),
    api_secret=os.getenv('API_SECRET', ''),
    testnet=testnet,
    base_url=BINANCE_BASE_URL
)

positions = {}

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
            .positions { background: #16213e; padding: 20px; border-radius: 10px; }
            table { width: 100%; border-collapse: collapse; }
            th, td { padding: 12px; text-align: left; border-bottom: 1px solid #333; }
            .buy { color: #00ff88; }
            .sell { color: #ff4444; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Trading Bot Dashboard</h1>
            <div class="status live">✅ LIVE - Webhook Active</div>
            <div class="status testnet">🔗 BINANCE TESTNET CONNECTED</div>
            
            <h2>💰 Balance</h2>
            <div id="balance">Loading...</div>
            
            <h2>📊 Positions</h2>
            <div class="positions">
                <table>
                    <tr><th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>P&L</th></tr>
                    <tbody id="positions">No positions</tbody>
                </table>
            </div>
        </div>
        
        <script>
            async function updateData() {
                try {
                    const balanceRes = await fetch('/api/balance');
                    const balance = await balanceRes.json();
                    document.getElementById('balance').innerHTML = `
                        <strong>USDT: $${balance.total}</strong> | 
                        <span class="buy">Total P&L: ${balance.pnl}</span>
                    `;
                    
                    const positionsRes = await fetch('/api/positions');
                    const positions = await positionsRes.json();
                    const tbody = document.getElementById('positions');
                    if (positions.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="5">No open positions</td></tr>';
                    } else {
                        tbody.innerHTML = positions.map(p => `
                            <tr>
                                <td>${p.symbol}</td>
                                <td class="${p.side.toLowerCase()}">${p.side}</td>
                                <td>${p.size}</td>
                                <td>$${p.entryPrice}</td>
                                <td class="${p.unrealizedPnl > 0 ? 'buy' : 'sell'}">
                                    $${p.unrealizedPnl.toFixed(4)}
                                </td>
                            </tr>
                        `).join('');
                    }
                } catch(e) { console.error(e); }
            }
            updateData();
            setInterval(updateData, 5000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/api/balance")
async def get_balance():
    try:
        account = client.futures_account()
        usdt = float(account['totalWalletBalance'])
        pnl = float(account['totalUnrealizedProfit'])
        return {"total": usdt, "pnl": pnl}
    except:
        return {"total": "N/A", "pnl": "N/A"}

@app.get("/api/positions")
async def get_positions():
    try:
        positions = client.futures_position_information()
        active = []
        for pos in positions:
            if float(pos['positionAmt']) != 0:
                active.append({
                    "symbol": pos['symbol'],
                    "side": "LONG" if float(pos['positionAmt']) > 0 else "SHORT",
                    "size": abs(float(pos['positionAmt'])),
                    "entryPrice": float(pos['entryPrice']),
                    "unrealizedPnl": float(pos['unrealizedProfit'])
                })
        return active
    except:
        return []

@app.post("/webhook")
async def webhook(request: Request):
    try:
        form = await request.form()
        symbol = form.get('symbol').upper()
        action = form.get('action').lower()
        price = float(form.get('price'))
        
        logger.info(f"🔔 {symbol} {action} ${price}")
        
        # تنفيذ الأوامر على Testnet
        if action in ['buy', 'sell']:
            quantity = 10 / price * 0.98  # 10 USDT مع 2% buffer
            
            order = client.futures_create_order(
                symbol=symbol,
                side=action.upper(),
                type="MARKET",
                quantity=round(quantity, 3)
            )
            
            result = f"✅ TESTNET {action.upper()}: {symbol} @ ${price:.2f} (ID: {order['orderId']})"
            logger.info(result)
            return {"status": "success", "message": result}
            
        elif action in ['tp', 'sl']:
            # إغلاق المركز الحالي
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
                    result = f"🧪 {action.upper()}: {symbol} CLOSED (ID: {order['orderId']})"
                    logger.info(result)
                    return {"status": "success", "message": result}
            
            return {"status": "no_position", "message": f"لا يوجد مركز مفتوح لـ {symbol}"}
            
    except BinanceAPIException as e:
        error = f"❌ Binance Error: {e.message}"
        logger.error(error)
        return {"status": "error", "message": error}
    except Exception as e:
        error = f"❌ Error: {str(e)}"
        logger.error(error)
        return {"status": "error", "message": error}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
