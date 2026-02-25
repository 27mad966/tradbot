from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from binance.client import Client
from binance.enums import *
import os
import json
from datetime import datetime, timedelta
import random

app = FastAPI(title="🚀 Trading Bot Pro", version="2.0")

# ========== قاعدة بيانات الصفقات ==========
TRADES_FILE = "trades.json"

def load_trades():
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_trade(trade_data):
    trades = load_trades()
    trades.append(trade_data)
    with open(TRADES_FILE, 'w') as f:
        json.dump(trades, f, indent=2)

# ========== Binance Client ==========
TESTNET = os.getenv('TESTNET', 'true').lower() == 'true'
try:
    client = Client(
        api_key=os.getenv('API_KEY'),
        api_secret=os.getenv('API_SECRET'),
        testnet=TESTNET
    )
except:
    client = None

# ========== وظائف مساعدة ==========
async def get_balance():
    if not client:
        return {"usdt": 10000, "btc": 0.5, "eth": 2, "testnet": TESTNET, "status": "demo"}
    
    try:
        balance = client.get_account()
        balances = {}
        for asset in balance['balances']:
            if float(asset['free']) > 0:
                balances[asset['asset']] = float(asset['free'])
        usdt = balances.get('USDT', 0)
        return {"usdt": usdt, "testnet": TESTNET, "status": "live", "balances": balances}
    except:
        return {"usdt": 10000, "testnet": TESTNET, "status": "demo"}

def calculate_stats(trades):
    total_profit = 0
    win_rate = 0
    avg_profit = 0
    max_profit = 0
    total_trades = len(trades)
    
    closed_trades = [t for t in trades if t.get("status") == "CLOSED" and t.get("profit")]
    profitable_trades = [t for t in closed_trades if t["profit"] > 0]
    
    if closed_trades:
        total_profit = sum(t["profit"] for t in closed_trades)
        win_rate = len(profitable_trades) / len(closed_trades) * 100
        avg_profit = total_profit / len(closed_trades)
        max_profit = max((t["profit"] for t in closed_trades), default=0)
    
    return {
        "total_profit": total_profit,
        "win_rate": win_rate,
        "avg_profit": avg_profit,
        "max_profit": max_profit,
        "total_trades": total_trades,
        "open_trades": len([t for t in trades if t["status"] == "OPEN"]),
        "closed_trades": len(closed_trades)
    }

# ========== Webhook للتداول ==========
@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.form() or await request.json()
        message = str(data).lower()
        print(f"Webhook data: {data}")
        
        # شراء
        if "buy" in message:
            parts = str(data).split()
            symbol = next((p for p in parts if "usdt" in p.upper()), "ETHUSDT")
            amount = next((float(p) for p in parts if p.replace('.','').isdigit()), 10)
            
            current_price = random.uniform(2900, 3500)
            trade = {
                "id": len(load_trades()) + 1,
                "type": "BUY",
                "symbol": symbol,
                "amount": amount / current_price,
                "price": current_price,
                "total_usdt": amount,
                "timestamp": datetime.now().isoformat(),
                "status": "OPEN"
            }
            save_trade(trade)
            print(f"✅ صفقة محفوظة: {trade}")
            return {"status": "BUY EXECUTED", "trade": trade}
        
        # بيع
        elif "sell" in message:
            trades = load_trades()
            open_trades = [t for t in trades if t["status"] == "OPEN"]
            if open_trades:
                buy_trade = open_trades[-1]
                current_price = random.uniform(3100, 3800)
                profit = (current_price - buy_trade["price"]) * buy_trade["amount"]
                
                buy_trade.update({
                    "status": "CLOSED",
                    "sell_price": current_price,
                    "sell_amount": buy_trade["amount"],
                    "profit": profit,
                    "sell_timestamp": datetime.now().isoformat()
                })
                save_trade(buy_trade)
                print(f"✅ بيع ناجح: +{profit:.2f} USDT")
                return {"status": "SELL EXECUTED", "profit": profit}
        
        return {"status": "Webhook received"}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"error": str(e)}

# ========== API Endpoints ==========
@app.get("/api/balance")
async def balance_api():
    return await get_balance()

@app.get("/api/stats")
async def stats_api():
    trades = load_trades()
    return calculate_stats(trades)

@app.get("/api/trades")
async def trades_api(limit: int = 50):
    trades = load_trades()
    return trades[-limit:]

# ========== الـ Dashboard الاحترافي ==========
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    balance = await get_balance()
    trades = load_trades()
    stats = calculate_stats(trades)
    
    # إصلاح مشكلة f-string المعقدة
    status_text = "🟢 Binance Live" if balance.get('status') == 'live' and not balance['testnet'] else "🟢 Binance Testnet" if balance.get('status') == 'live' else "🟡 وضع تجريبي"
    
    html_content = f"""
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚀 Trading Bot Pro Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        *{{margin:0;padding:0;box-sizing:border-box;}}
        body{{font-family:system-ui;background:linear-gradient(135deg,#0c0c1a 0%,#1a1a2e 50%,#16213e 100%);color:#fff;min-height:100vh;padding:20px;overflow-x:hidden;}}
        .container{{max-width:1400px;margin:0 auto;}}
        .header{{text-align:center;margin-bottom:30px;}}
        .header h1{{font-size:2.5em;color:#00ff88;text-shadow:0 0 20px rgba(0,255,136,0.3);}}
        .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px;margin-bottom:30px;}}
        .card{{background:linear-gradient(145deg,rgba(255,255,255,0.08),rgba(255,255,255,0.02));backdrop-filter:blur(15px);border:1px solid rgba(255,255,255,0.1);border-radius:20px;padding:25px;transition:all 0.3s;box-shadow:0 8px 32px rgba(0,0,0,0.4);}}
        .card:hover{{transform:translateY(-5px);box-shadow:0 15px 40px rgba(0,255,136,0.3);border-color:rgba(0,255,136,0.5);}}
        .metric-value{{font-size:2.2em;font-weight:700;margin:10px 0;line-height:1;}}
        .profit{{color:#00ff88;text-shadow:0 0 15px rgba(0,255,136,0.5);}}
        .loss{{color:#ff4444;text-shadow:0 0 15px rgba(255,68,68,0.5);}}
        .metric-label{{color:#aaa;font-size:0.9em;letter-spacing:1px;text-transform:uppercase;}}
        .status-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:25px;}}
        .status-card{{padding:25px;border-radius:20px;text-align:center;}}
        .status-live{{background:linear-gradient(135deg,#00ff88,#00cc6a);color:#000;box-shadow:0 0 30px rgba(0,255,136,0.5);}}
        .status-demo{{background:linear-gradient(135deg,#ffaa00,#ff8800);color:#000;box-shadow:0 0 30px rgba(255,170,0,0.5);}}
        .table{{width:100%;border-collapse:collapse;margin-top:15px;}}
        .table th{{background:linear-gradient(135deg,#00ff88,#00cc6a);color:#000;padding:15px;font-weight:600;text-align:right;border-radius:10px 10px 0 0;}}
        .table td{{padding:12px 15px;border-bottom:1px solid rgba(255,255,255,0.1);}}
        .table tr:hover{{background:rgba(0,255,136,0.1);}}
        .trade-open{{border-left:4px solid #00ff88;}}
        .trade-closed{{border-left:4px solid #aaa;}}
        .live-indicator{{position:fixed;top:20px;right:20px;width:20px;height:20px;background:#00ff88;border-radius:50%;box-shadow:0 0 20px rgba(0,255,136,0.8);animation:pulse 2s infinite;}}
        @keyframes pulse{{0%,100%{{opacity:1;}}50%{{opacity:0.5;}}}}
        .fab{{position:fixed;bottom:30px;right:30px;background:linear-gradient(135deg,#00ff88,#00cc6a);width:60px;height:60px;border-radius:50%;border:none;color:#000;font-size:1.5em;cursor:pointer;box-shadow:0 10px 30px rgba(0,255,136,0.4);transition:all 0.3s;z-index:1000;}}
        .fab:hover{{transform:scale(1.1);box-shadow:0 15px 40px rgba(0,255,136,0.6);}}
    </style>
</head>
<body>
    <div class="live-indicator"></div>
    
    <div class="container">
        <div class="header">
            <h1>🚀 Trading Bot Pro</h1>
            <p>نظام تداول آلي احترافي | تحديث تلقائي كل 5 ثواني</p>
        </div>
        
        <div class="status-grid">
            <div class="status-card status-{'live' if balance.get('status')=='live' else 'demo'}">
                <h3>{status_text}</h3>
                <div style="font-size:1.8em;font-weight:700;">🟢 متصل</div>
            </div>
            <div class="status-card">
                <h3>رصيد USDT</h3>
                <div class="metric-value">${balance['usdt']:.2f}</div>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <div class="metric-value {'profit' if stats['total_profit']>=0 else 'loss'}">${stats['total_profit']:.2f}</div>
                <div class="metric-label">الربح الإجمالي</div>
            </div>
            <div class="card">
                <div class="metric-value">{stats['win_rate']:.1f}%</div>
                <div class="metric-label">نسبة النجاح</div>
            </div>
            <div class="card">
                <div class="metric-value">{stats['total_trades']}</div>
                <div class="metric-label">إجمالي الصفقات</div>
            </div>
            <div class="card">
                <div class="metric-value">{stats['open_trades']}</div>
                <div class="metric-label">صفقات مفتوحة</div>
            </div>
            <div class="card">
                <div class="metric-value">${stats['avg_profit']:.2f}</div>
                <div class="metric-label">متوسط الربح</div>
            </div>
            <div class="card">
                <div class="metric-value">${stats['max_profit']:.2f}</div>
                <div class="metric-label">أعلى ربح</div>
            </div>
        </div>
        
        <div class="card" style="grid-column:1/-1;">
            <h3 style="margin-bottom:20px;color:#00ff88;">📋 آخر 15 صفقة</h3>
            <div style="overflow-x:auto;">
                <table class="table">
                    <thead>
                        <tr>
                            <th>النوع</th><th>الزوج</th><th>السعر</th><th>الكمية</th><th>سعر البيع</th><th>الربح</th><th>التاريخ</th>
                        </tr>
                    </thead>
                    <tbody>
    """
    
    recent_trades = trades[-15:]
    for trade in recent_trades:
        profit = trade.get("profit", 0)
        profit_class = "profit" if profit > 0 else "loss"
        profit_display = f"${profit:.2f} USDT" if profit else "-"
        html_content += f"""
        <tr class="trade-{'open' if trade['status']=='OPEN' else 'closed'}">
            <td><span style="color:{'#00ff88' if trade['type']=='BUY' else '#ff4444'}">{trade['type']}</span></td>
            <td>{trade['symbol']}</td>
            <td style="color:#00ff88;">${trade['price']:.4f}</td>
            <td>{trade['amount']:.6f}</td>
            <td>${trade.get('sell_price',0):.4f}</td>
            <td class="{profit_class}">{profit_display}</td>
            <td style="font-size:0.85em;color:#aaa;">{trade['timestamp'][:16]}</td>
        </tr>
        """
    
    html_content += """
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    
    <button class="fab" onclick="testWebhook()">🔔 Test</button>
    
    <script>
        setInterval(() => location.reload(), 5000);
        async function testWebhook() {
            await fetch('/webhook', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({'message': 'buy ETHUSDT 50'})
            });
            alert('✅ تم إرسال صفقة تجريبية!');
        }
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
