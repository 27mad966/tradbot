from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import json
import os
from datetime import datetime, timedelta
import random

app = FastAPI(title="🚀 Trading Bot Pro v6.1 - Professional Dashboard")

TRADES_FILE = "trades.json"
BALANCE_FILE = "balance.json"

MARKET_NEWS = [
    "🔔 FOMC Rate Decision Tomorrow - Markets Expecting 25bps Cut",
    "📈 Bitcoin ETF Inflows Hit $2.1B - New ATH",
    "⚠️ US CPI Data in 2 Hours - Core Inflation 3.2%",
    "🚀 ETH ETF Launch Confirmed - $500M First Day",
    "💥 SOL Breaks $250 - Next Target $300",
    "📉 BTC Dips to $92K Support - RSI Oversold"
]

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

# Initialize balance
BALANCE = load_data(BALANCE_FILE, {
    "usdt": 10245.67, "total_profit": 245.67, "pnl_percent": 2.46,
    "win_rate": 67.3, "total_trades": 45, "daily_pnl": 89.23
})

@app.get("/api/balance")
async def get_balance():
    return BALANCE

@app.get("/api/trades")
async def get_trades_api():
    trades = load_trades()[-20:]
    total_profit = sum(t.get('profit', 0) for t in trades)
    return {"trades": trades, "total_profit": total_profit, "count": len(trades)}

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        symbol = data.get("symbol", "UNKNOWN").upper()
        action = data.get("action", "BUY").upper()
        price = float(data.get("price", random.uniform(50, 200)))
        amount = float(data.get("amount", random.uniform(5, 50)))
        
        # Simulate realistic P&L
        if random.random() < 0.6:
            exit_price = price * (1 + random.uniform(0.02, 0.12))
            profit = amount * (exit_price - price)
        else:
            exit_price = price * (1 - random.uniform(0.01, 0.08))
            profit = amount * (exit_price - price)
        
        trade = {
            "id": len(load_trades()) + 1,
            "time": datetime.utcnow().isoformat() + "Z",
            "symbol": symbol, "action": action,
            "entry_price": price, "exit_price": exit_price,
            "amount": amount, "profit": round(profit, 2),
            "pnl_percent": round((profit/amount)*100, 1)
        }
        
        save_trade(trade)
        BALANCE["total_profit"] += profit
        BALANCE["total_trades"] += 1
        save_data(BALANCE_FILE, BALANCE)
        
        return {"status": "OK", "trade": trade}
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}

@app.get("/ping")
async def ping():
    return {"status": "alive"}

@app.get("/")
async def dashboard():
    trades = load_trades()[-15:]
    total_profit = sum(t.get('profit', 0) for t in trades)
    
    # Build trades table HTML safely
    trades_html = ""
    for trade in trades:
        profit = trade.get('profit', 0)
        profit_class = "profit" if profit > 0 else "loss"
        trades_html += """
        <tr>
            <td>{}</td>
            <td><span class="symbol">{}</span></td>
            <td><span class="action {}">{}</span></td>
            <td style="color: #00D4AA;">${:.4f}</td>
            <td>{:.3f}</td>
            <td class="{}"><strong>${:.2f}</strong><span style="font-size: 0.8em;">({}%)</span></td>
        </tr>
        """.format(
            trade.get('time', 'N/A')[:16],
            trade.get('symbol', 'N/A'),
            trade.get('action', '').lower(),
            trade.get('action', 'N/A'),
            trade.get('entry_price', 0),
            trade.get('amount', 0),
            profit_class,
            profit,
            abs(trade.get('pnl_percent', 0))
        )
    
    html = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <title>🚀 Trading Bot Pro v6.1 | داشبورد احترافي</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-primary: linear-gradient(135deg, #0F0F23 0%, #1A1A2E 50%, #16213E 100%);
            --glass: rgba(255,255,255,0.05);
            --glass-border: rgba(255,255,255,0.1);
            --neon-green: #00D4AA;
            --neon-pink: #FF6B9D;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: "SF Pro Display", -apple-system, Inter, sans-serif;
            background: var(--bg-primary); color: white; min-height: 100vh; 
        }
        .container { 
            max-width: 1600px; margin: 0 auto; padding: 20px;
            display: grid; grid-template-columns: 350px 1fr 350px; gap: 25px;
        }
        .glass-card { 
            background: var(--glass); backdrop-filter: blur(25px); 
            border-radius: 24px; border: 1px solid var(--glass-border);
            padding: 30px; margin-bottom: 20px; box-shadow: 0 25px 45px rgba(0,0,0,0.3);
        }
        .header { 
            display: flex; align-items: center; gap: 15px; margin-bottom: 25px;
            padding-bottom: 20px; border-bottom: 1px solid var(--glass-border);
        }
        .status-live { 
            width: 12px; height: 12px; border-radius: 50%; 
            background: var(--neon-green); animation: pulse 2s infinite; 
        }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
        .balance-total { 
            font-size: 2.5em; font-weight: 800; 
            background: linear-gradient(135deg, var(--neon-green), #00A085);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }
        .stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin: 20px 0; }
        .stat-card { text-align: center; padding: 20px; background: var(--glass); border-radius: 16px; border: 1px solid var(--glass-border); }
        .stat-value { font-size: 1.8em; font-weight: bold; margin-bottom: 5px; }
        .profit { color: var(--neon-green) !important; }
        .loss { color: #FF6B6B !important; }
        .trades-table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
        .trades-table th { padding: 15px 12px; text-align: right; font-weight: 600; background: rgba(255,255,255,0.03); border-bottom: 1px solid var(--glass-border); }
        .trades-table td { padding: 12px; border-bottom: 1px solid var(--glass-border); }
        .symbol { font-weight: 700; font-size: 0.95em; }
        .action.buy { color: var(--neon-green); } 
        .action.sell { color: var(--neon-pink); }
        .news-ticker { background: rgba(0,212,170,0.15); padding: 12px 20px; border-radius: 12px; margin: 20px 0; overflow: hidden; }
        .news { animation: scroll 40s linear infinite; white-space: nowrap; font-size: 0.9em; font-weight: 500; }
        @keyframes scroll { 0% { transform: translateX(100%); } 100% { transform: translateX(-100%); } }
        #pnlChart { height: 250px; margin-top: 20px; }
        @media (max-width: 1200px) { .container { grid-template-columns: 1fr; } }
        @media (max-width: 768px) { .container { padding: 10px; } .glass-card { padding: 20px; } }
        button { 
            background: linear-gradient(135deg, var(--neon-green), #00A085); color: white; 
            border: none; padding: 12px 24px; border-radius: 12px; cursor: pointer; 
            font-weight: 600; transition: all 0.3s; font-family: inherit;
        }
        button:hover { transform: translateY(-2px); box-shadow: 0 15px 35px rgba(0,212,170,0.4); }
    </style>
</head>
<body>
    <div class="container">
        <div class="glass-card">
            <div class="header">
                <div class="status-live"></div>
                <h1 style="margin: 0; font-size: 1.4em; color: var(--neon-green);">🚀 Trading Bot Pro</h1>
                <span style="font-size: 0.8em; opacity: 0.8;">v6.1</span>
            </div>
            <div class="balance-total" id="totalBalance">$10,245.67</div>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value profit" id="pnlValue">$245.67</div>
                    <div style="font-size: 0.85em; opacity: 0.8;">Total P&L</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="winRate">67.3%</div>
                    <div style="font-size: 0.85em; opacity: 0.8;">Win Rate</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="totalTrades">45</div>
                    <div style="font-size: 0.85em; opacity: 0.8;">Total Trades</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value profit" id="dailyPnl">$89.23</div>
                    <div style="font-size: 0.85em; opacity: 0.8;">24h P&L</div>
                </div>
            </div>
            <div class="news-ticker">
                <div class="news">🔥 ''' + ' | '.join(MARKET_NEWS) + ''' 🔥 Live Market Updates →</div>
            </div>
            <button onclick="testWebhook()">🧪 Test Webhook</button>
        </div>
        
        <div class="glass-card">
            <div class="header">
                <h2 style="margin: 0;">📈 P&L Chart (30 Day)</h2>
                <div style="font-size: 0.9em; opacity: 0.8;">Live Updates</div>
            </div>
            <canvas id="pnlChart"></canvas>
        </div>
        
        <div class="glass-card">
            <div class="header">
                <h2 style="margin: 0;">📊 Recent Trades (15)</h2>
                <span style="font-size: 0.9em; opacity: 0.8;" id="tradesCount">0 trades</span>
            </div>
            <table class="trades-table" id="tradesTable">
                <thead>
                    <tr>
                        <th>الوقت</th><th>الرمز</th><th>النوع</th><th>السعر</th><th>الكمية</th><th>P&L</th>
                    </tr>
                </thead>
                <tbody>''' + trades_html + '''</tbody>
            </table>
            <button onclick="location.reload()" style="width: 100%; margin-top: 15px;">🔄 Refresh</button>
        </div>
    </div>

    <script>
        let chart = null;
        
        async function updateDashboard() {
            try {
                const balanceRes = await fetch('/api/balance');
                const balance = await balanceRes.json();
                
                const tradesRes = await fetch('/api/trades');
                const tradesData = await tradesRes.json();
                
                document.getElementById("totalBalance").textContent = "$" + balance.usdt.toLocaleString();
                document.getElementById("pnlValue").textContent = "$" + balance.total_profit.toLocaleString();
                document.getElementById("winRate").textContent = balance.win_rate + "%";
                document.getElementById("totalTrades").textContent = balance.total_trades;
                document.getElementById("dailyPnl").textContent = "$" + balance.daily_pnl;
                
                document.getElementById("tradesCount").textContent = tradesData.count + " trades";
                const tbody = document.querySelector("#tradesTable tbody");
                tbody.innerHTML = tradesData.trades.map(trade => `
                    <tr>
                        <td>${trade.time ? trade.time.slice(0,16) : "N/A"}</td>
                        <td><span class="symbol">${trade.symbol}</span></td>
                        <td><span class="action ${trade.action ? trade.action.toLowerCase() : ""}">${trade.action || "N/A"}</span></td>
                        <td style="color: #00D4AA;">$${parseFloat(trade.entry_price || 0).toFixed(4)}</td>
                        <td>${parseFloat(trade.amount || 0).toFixed(3)}</td>
                        <td class="${trade.profit > 0 ? "profit" : "loss"}">
                            <strong>$${parseFloat(trade.profit || 0).toFixed(2)}</strong>
                            <span style="font-size: 0.8em;">(${parseFloat(trade.pnl_percent || 0).toFixed(1)}%)</span>
                        </td>
                    </tr>
                `).join("");
                
                updateChart(tradesData.trades);
            } catch(e) {
                console.log("Update failed:", e);
            }
        }
        
        function updateChart(trades) {
            const ctx = document.getElementById("pnlChart").getContext("2d");
            const labels = trades.slice(-30).map(t => new Date(t.time).toLocaleDateString());
            const data = trades.slice(-30).map(t => t.profit || 0);
            const cumulative = data.reduce((acc, val) => {
                acc.push((acc[acc.length-1] || 0) + val);
                return acc;
            }, []);
            
            if (chart) chart.destroy();
            chart = new Chart(ctx, {
                type: "line",
                data: {
                    labels: labels,
                    datasets: [{
                        label: "Cumulative P&L ($)",
                        data: cumulative,
                        borderColor: "#00D4AA",
                        backgroundColor: "rgba(0,212,170,0.1)",
                        tension: 0.4,
                        fill: true,
                        pointRadius: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { grid: { color: "rgba(255,255,255,0.1)" }, ticks: { color: "white" } },
                        x: { grid: { color: "rgba(255,255,255,0.1)" }, ticks: { color: "white", maxTicksLimit: 10 } }
                    }
                }
            });
        }
        
        async function testWebhook() {
            const symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"];
            const symbol = symbols[Math.floor(Math.random() * symbols.length)];
            
            const response = await fetch("/webhook", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    symbol: symbol,
                    action: Math.random() > 0.5 ? "BUY" : "SELL",
                    price: (100 + Math.random() * 200).toFixed(2),
                    amount: (10 + Math.random() * 40).toFixed(2)
                })
            });
            
            if (response.ok) {
                alert("✅ تم تنفيذ صفقة تجريبية: " + symbol);
                updateDashboard();
            } else {
                alert("❌ خطأ في تنفيذ الصفقة");
            }
        }
        
        updateDashboard();
        setInterval(updateDashboard, 3000);
    </script>
</body>
</html>
    '''.replace("''' + ' | '.join(MARKET_NEWS) + '''", ' | '.join(MARKET_NEWS))
    
    return HTMLResponse(content=html, status_code=200)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
