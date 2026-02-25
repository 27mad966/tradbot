from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
import json
import os
from datetime import datetime, timedelta
import random

app = FastAPI(title="🚀 Trading Bot Pro v5.0")

TRADES_FILE = "trades.json"
MARKET_NEWS = [
    "🔔 FOMC Rate Decision Tomorrow - Markets Expecting 25bps Cut",
    "📈 Bitcoin ETF Approval Rumors - SEC Meeting Next Week", 
    "⚠️ US CPI Data Release in 2 Hours - Inflation Expectations High",
    "🚀 ETH ETF Launch Confirmed - Institutional Buying Expected"
]
BALANCE = {"usdt": 10245.67, "profit": 245.67, "pnl": "2.46%"}

def load_trades():
    try:
        if os.path.exists(TRADES_FILE):
            with open(TRADES_FILE, 'r') as f:
                return json.load(f)
        return []
    except:
        return []

def save_trade(trade_data):
    trades = load_trades()
    trades.append(trade_data)
    # Keep only last 3 months (flexible)
    cutoff = datetime.now() - timedelta(days=90)
    trades = [t for t in trades if datetime.fromisoformat(t['time'].replace('Z', '+00:00')) > cutoff]
    with open(TRADES_FILE, 'w') as f:
        json.dump(trades, f, indent=2)

@app.get("/")
async def dashboard():
    trades = load_trades()[-15:]  # Last 15 trades
    trades_html = ""
    total_profit = sum(t.get('profit', 0) for t in trades)
    
    for trade in trades:
        profit_class = "profit" if trade.get("profit", 0) > 0 else "loss"
        trades_html += f"""
        <tr>
            <td>{trade.get('time', 'N/A')[:16]}</td>
            <td><strong>{trade.get('symbol', 'N/A')}</strong></td>
            <td>{trade.get('action', 'N/A')}</td>
            <td style="color: #00D4AA;">${trade.get('price', 0):.2f}</td>
            <td>{trade.get('amount', 0):.1f}</td>
            <td class="{profit_class}">${trade.get('profit', 0):.2f}</td>
        </tr>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🚀 Trading Bot Pro v5.0</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{ font-family: 'Inter', -apple-system, sans-serif; background: linear-gradient(135deg, #0F0F23 0%, #1A1A2E 100%); color: white; min-height: 100vh; }}
            .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; display: grid; grid-template-columns: 1fr 2fr; gap: 20px; }}
            .sidebar {{ background: rgba(255,255,255,0.05); backdrop-filter: blur(20px); border-radius: 20px; padding: 30px; border: 1px solid rgba(255,255,255,0.1); }}
            .main {{ background: rgba(255,255,255,0.05); backdrop-filter: blur(20px); border-radius: 20px; padding: 30px; border: 1px solid rgba(255,255,255,0.1); }}
            .balance-card {{ background: linear-gradient(135deg, #00D4AA, #00A085); border-radius: 15px; padding: 20px; margin-bottom: 20px; text-align: center; }}
            .profit {{ color: #00D4AA; font-weight: bold; }}
            .loss {{ color: #FF6B6B; font-weight: bold; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }}
            th {{ background: rgba(255,255,255,0.05); }}
            .news-ticker {{ background: rgba(0,212,170,0.2); padding: 15px; border-radius: 10px; margin-bottom: 20px; overflow: hidden; }}
            .news {{ animation: scroll 30s linear infinite; white-space: nowrap; }}
            @keyframes scroll {{ 0% {{ transform: translateX(100%); }} 100% {{ transform: translateX(-100%); }} }}
            button {{ background: linear-gradient(135deg, #00D4AA, #00A085); color: white; border: none; padding: 12px 24px; border-radius: 10px; cursor: pointer; font-weight: bold; transition: all 0.3s; }}
            button:hover {{ transform: scale(1.05); box-shadow: 0 10px 30px rgba(0,212,170,0.4); }}
            @media (max-width: 768px) {{ .container {{ grid-template-columns: 1fr; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="sidebar">
                <h1 style="color: #00D4AA; margin-bottom: 20px;">🚀 Trading Bot Pro</h1>
                <div class="balance-card">
                    <h2>💰 Balance</h2>
                    <p>USDT: ${BALANCE['usdt']}</p>
                    <p class="profit">P&L: ${BALANCE['profit']} ({BALANCE['pnl']})</p>
                    <p>Total Profit: ${total_profit:.2f}</p>
                </div>
                <div class="news-ticker">
                    <div class="news">
                        {' | '.join(MARKET_NEWS)} → Live Updates →
                    </div>
                </div>
                <button onclick="location.reload()">🔄 Refresh</button>
            </div>
            <div class="main">
                <h2>📊 Recent Trades (Last 15)</h2>
                <table>
                    <tr><th>Time</th><th>Symbol</th><th>Action</th><th>Price</th><th>Amount</th><th>P&L</th></tr>
                    {trades_html}
                </table>
            </div>
        </div>
        <script>
            setInterval(() => location.reload(), 5000);  // Auto refresh every 5s
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html, status_code=200)

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        symbol = data.get("symbol", "UNKNOWN").upper()
        action = data.get("action", "BUY").upper()
        price = float(data.get("price", random.uniform(50, 100)))
        amount = float(data.get("amount", 10.0))
        
        # Simulate trade execution & P&L
        entry_price = price
        exit_price = price * (1 + random.uniform(-0.05, 0.1))  # Random P&L
        profit = amount * (exit_price - entry_price)
        
        trade = {
            "time": datetime.utcnow().isoformat() + "Z",
            "symbol": symbol,
            "action": action,
            "price": entry_price,
            "amount": amount,
            "profit": round(profit, 2)
        }
        save_trade(trade)
        
        return {"status": "OK", "trade": trade, "message": f"{action} {symbol} executed"}
    except Exception as e:
        return {"status": "Error", "error": str(e)}

@app.get("/ping")
async def ping():
    return {"status": "alive"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
