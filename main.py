from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import json
import os
from datetime import datetime, timedelta
import random

app = FastAPI(title="Trading Bot Pro v7.0 - محفظة مفصلة")

TRADES_FILE = "trades.json"
BALANCE_FILE = "balance.json"
PORTFOLIO_FILE = "portfolio.json"

def load_data(file_path, default=None):
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        return default or {}
    except:
        return default or {}

def save_data(file_path, data):
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
    except:
        pass

def load_trades():
    trades = load_data(TRADES_FILE, [])
    cutoff = datetime.now() - timedelta(days=90)
    filtered = []
    for trade in trades:
        try:
            if 'time' in trade:
                trade_time = datetime.fromisoformat(trade['time'].replace('Z', '+00:00'))
                if trade_time > cutoff:
                    filtered.append(trade)
        except:
            filtered.append(trade)
    return filtered

def save_trade(trade_data):
    trades = load_trades()
    trades.append(trade_data)
    save_data(TRADES_FILE, trades)

def update_portfolio(symbol, action, amount, price):
    portfolio = load_data(PORTFOLIO_FILE, {"USDT": 10000.0, "positions": {}})
    
    if action == "BUY":
        cost = amount * price
        if portfolio["USDT"] >= cost:
            portfolio["USDT"] -= cost
            if symbol not in portfolio["positions"]:
                portfolio["positions"][symbol] = 0
            portfolio["positions"][symbol] += amount
    elif action == "SELL":
        if symbol in portfolio["positions"] and portfolio["positions"][symbol] >= amount:
            portfolio["positions"][symbol] -= amount
            proceeds = amount * price
            portfolio["USDT"] += proceeds
    
    # Clean zero positions
    portfolio["positions"] = {k: v for k, v in portfolio["positions"].items() if v > 0}
    save_data(PORTFOLIO_FILE, portfolio)
    return portfolio

# Initialize data
BALANCE = load_data(BALANCE_FILE, {"total_value": 10245.67, "total_profit": 245.67, "total_trades": 0})
PORTFOLIO = load_data(PORTFOLIO_FILE, {"USDT": 10000.0, "positions": {}})

@app.get("/api/portfolio")
async def get_portfolio():
    portfolio = load_data(PORTFOLIO_FILE, {"USDT": 10000.0, "positions": {}})
    trades = load_trades()
    
    total_value = portfolio["USDT"]
    positions_value = 0
    unrealized_pnl = 0
    
    # Calculate portfolio value and unrealized P&L (using last trade price as reference)
    for symbol, qty in portfolio["positions"].items():
        # Simulate current price from recent trades
        recent_price = 100.0  # Default
        for trade in trades[-10:]:
            if trade.get("symbol") == symbol:
                recent_price = trade.get("entry_price", 100.0)
                break
        
        value = qty * recent_price
        total_value += value
        positions_value += value
    
    return {
        "cash_usdt": round(portfolio["USDT"], 2),
        "positions": portfolio["positions"],
        "positions_value": round(positions_value, 2),
        "total_value": round(total_value, 2),
        "cash_percent": round((portfolio["USDT"]/total_value)*100, 1) if total_value > 0 else 0,
        "positions_percent": round((positions_value/total_value)*100, 1) if total_value > 0 else 0
    }

@app.get("/api/trades")
async def get_trades():
    trades = load_trades()[-20:]
    total_profit = sum(t.get('profit', 0) for t in trades)
    wins = len([t for t in trades if t.get('profit', 0) > 0])
    win_rate = (wins/len(trades)*100) if trades else 0
    return {"trades": trades, "total_profit": total_profit, "win_rate": round(win_rate, 1), "count": len(trades)}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        symbol = data.get("symbol", "BTCUSDT").upper()
        action = data.get("action", "BUY").upper()
        price = float(data.get("price", random.uniform(50, 200)))
        amount = float(data.get("amount", random.uniform(5, 50)))
        
        # Simulate trade execution with realistic P&L
        portfolio = update_portfolio(symbol, action, amount, price)
        
        if random.random() < 0.6:  # 60% win rate
            exit_price = price * (1 + random.uniform(0.02, 0.12))
        else:
            exit_price = price * (1 - random.uniform(0.01, 0.08))
        
        profit = amount * (exit_price - price)
        
        trade = {
            "id": len(load_trades()) + 1,
            "time": datetime.utcnow().isoformat() + "Z",
            "symbol": symbol,
            "action": action,
            "side": "LONG" if action == "BUY" else "SHORT",
            "entry_price": round(price, 4),
            "exit_price": round(exit_price, 4),
            "amount": round(amount, 3),
            "cost": round(amount * price, 2),
            "proceeds": round(amount * exit_price, 2),
            "profit": round(profit, 2),
            "pnl_percent": round((profit/(amount*price))*100, 1)
        }
        
        save_trade(trade)
        BALANCE["total_trades"] += 1
        BALANCE["total_profit"] += profit
        save_data(BALANCE_FILE, BALANCE)
        
        return {"status": "EXECUTED", "trade": trade, "portfolio": portfolio}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}

@app.get("/ping")
async def ping():
    return {"status": "alive"}

@app.get("/")
async def dashboard():
    portfolio = load_data(PORTFOLIO_FILE, {"USDT": 10000.0, "positions": {}})
    trades = load_trades()[-15:]
    
    # Portfolio summary
    total_value = portfolio["USDT"]
    for symbol, qty in portfolio["positions"].items():
        total_value += qty * 100  # Simplified valuation
    
    trades_html = ""
    for trade in trades:
        profit = trade.get('profit', 0)
        pnl_class = "profit" if profit > 0 else "loss"
        trades_html += """
        <tr>
            <td>{}</td><td>{}</td><td>{}</td><td class="symbol">{}</td>
            <td style="color: #00D4AA;">${:,.4f}</td><td>${:,.2f}</td><td>${:,.2f}</td>
            <td class="{}">${:,.2f}</td><td>{:+.1f}%</td>
        </tr>
        """.format(
            trade.get('time', 'N/A')[:16],
            trade.get('action', 'N/A'),
            trade.get('side', 'N/A'),
            trade.get('symbol', 'N/A'),
            trade.get('entry_price', 0),
            trade.get('cost', 0),
            trade.get('proceeds', 0),
            pnl_class,
            trade.get('profit', 0),
            trade.get('pnl_percent', 0)
        )
    
    html = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <title>Trading Bot Pro v7.0 - محفظة التداول</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: Arial, sans-serif; 
            background: #1a1a2e; color: white; padding: 20px; line-height: 1.6;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { 
            text-align: center; padding: 20px; background: #16213e; 
            border-radius: 10px; margin-bottom: 20px;
        }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        .card { 
            background: #0f0f23; border-radius: 10px; padding: 25px; 
            border: 1px solid #333;
        }
        .card h3 { color: #00D4AA; margin-bottom: 15px; font-size: 1.3em; }
        .portfolio-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; }
        .metric { text-align: center; padding: 15px; background: #1a1a2e; border-radius: 8px; }
        .metric-value { font-size: 1.8em; font-weight: bold; margin-bottom: 5px; }
        .profit { color: #00D4AA; }
        .loss { color: #ff4444; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 0.9em; }
        th, td { padding: 12px 8px; text-align: right; border-bottom: 1px solid #333; }
        th { background: #16213e; font-weight: bold; }
        .symbol { font-weight: bold; color: #00D4AA; font-size: 0.95em; }
        tr:hover { background: rgba(0,212,170,0.1); }
        button { 
            background: #00D4AA; color: white; border: none; 
            padding: 12px 24px; border-radius: 6px; cursor: pointer; 
            font-weight: bold; margin: 5px;
        }
        button:hover { background: #00A085; }
        @media (max-width: 768px) { 
            .grid { grid-template-columns: 1fr; } 
            .portfolio-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Trading Bot Pro v7.0</h1>
            <p>داشبورد تداول احترافي - بيانات مفصلة ودقيقة</p>
        </div>
        
        <div class="grid">
            <div class="card">
                <h3>💰 حالة المحفظة</h3>
                <div id="portfolio-metrics" class="portfolio-grid">
                    <div class="metric">
                        <div class="metric-value" id="total-value">$<span>0</span></div>
                        <div>إجمالي القيمة</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value" id="cash-usdt">$<span>0</span></div>
                        <div>نقد USDT</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value" id="positions-value">$<span>0</span></div>
                        <div>قيمة المراكز</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value" id="total-profit" class="profit">$<span>0</span></div>
                        <div>إجمالي الربح</div>
                    </div>
                </div>
            </div>
            
            <div class="card">
                <h3>📊 الإحصائيات</h3>
                <div class="portfolio-grid">
                    <div class="metric">
                        <div class="metric-value" id="total-trades">0</div>
                        <div>إجمالي الصفقات</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value" id="win-rate">0%</div>
                        <div>نسبة النجاح</div>
                    </div>
                    <div class="metric">
                        <div class="metric-value profit" id="daily-pnl">$0</div>
                        <div>الربح اليومي</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h3>📈 آخر الصفقات (15)</h3>
            <button onclick="testTrade()">🧪 اختبار صفقة</button>
            <button onclick="location.reload()">🔄 تحديث</button>
            <div style="margin-top: 20px;">
                <table id="trades-table">
                    <thead>
                        <tr>
                            <th>الوقت</th><th>النوع</th><th>الجانب</th><th>الرمز</th>
                            <th>سعر الدخول</th><th>التكلفة</th><th>الإيراد</th><th>الربح</th><th>P&L%</th>
                        </tr>
                    </thead>
                    <tbody>''' + trades_html + '''</tbody>
                </table>
            </div>
        </div>
        
        <div style="margin-top: 20px; padding: 15px; background: #16213e; border-radius: 10px; font-size: 0.9em;">
            <strong>مواعيد التحديث:</strong> كل 3 ثواني | 
            <strong>حالة الخادم:</strong> <span style="color: #00D4AA;">متصل ✅</span> |
            <strong>الصفقات المحفوظة:</strong> ''' + str(len(load_trades())) + '''
        </div>
    </div>

    <script>
        async function updateDashboard() {
            try {
                // Portfolio data
                const portfolioRes = await fetch('/api/portfolio');
                const portfolio = await portfolioRes.json();
                
                document.getElementById('total-value').textContent = portfolio.total_value.toLocaleString();
                document.getElementById('cash-usdt').firstChild.textContent = portfolio.cash_usdt.toLocaleString();
                document.getElementById('positions-value').firstChild.textContent = portfolio.positions_value.toLocaleString();
                
                // Trades data
                const tradesRes = await fetch('/api/trades');
                const tradesData = await tradesRes.json();
                
                document.getElementById('total-trades').textContent = tradesData.count;
                document.getElementById('win-rate').textContent = tradesData.win_rate + '%';
                document.getElementById('total-profit').firstChild.textContent = tradesData.total_profit.toLocaleString();
                
                // Update trades table
                const tbody = document.querySelector('#trades-table tbody');
                tbody.innerHTML = tradesData.trades.map(trade => `
                    <tr>
                        <td>${trade.time ? trade.time.slice(0,16) : 'N/A'}</td>
                        <td>${trade.action || 'N/A'}</td>
                        <td>${trade.side || 'N/A'}</td>
                        <td class="symbol">${trade.symbol || 'N/A'}</td>
                        <td style="color: #00D4AA;">$${parseFloat(trade.entry_price || 0).toLocaleString('en-US', {minimumFractionDigits: 4, maximumFractionDigits: 4})}</td>
                        <td>$${parseFloat(trade.cost || 0).toLocaleString()}</td>
                        <td>$${parseFloat(trade.proceeds || 0).toLocaleString()}</td>
                        <td class="${trade.profit > 0 ? 'profit' : 'loss'}">
                            $${parseFloat(trade.profit || 0).toLocaleString()}
                        </td>
                        <td>${parseFloat(trade.pnl_percent || 0).toFixed(1)}%</td>
                    </tr>
                `).join('');
                
            } catch(e) {
                console.log('تحديث فشل:', e);
            }
        }
        
        async function testTrade() {
            const symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'];
            const symbol = symbols[Math.floor(Math.random() * symbols.length)];
            
            const res = await fetch('/webhook', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    symbol: symbol,
                    action: Math.random() > 0.5 ? 'BUY' : 'SELL',
                    price: (80 + Math.random() * 150),
                    amount: (5 + Math.random() * 25)
                })
            });
            
            if (res.ok) {
                alert('✅ تم تنفيذ صفقة تجريبية: ' + symbol);
                updateDashboard();
            }
        }
        
        // تحديث كل 3 ثواني
        updateDashboard();
        setInterval(updateDashboard, 3000);
    </script>
</body>
</html>
    '''
    
    return HTMLResponse(content=html, status_code=200)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
