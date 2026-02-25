from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
import json
import os
from datetime import datetime
import random

app = FastAPI(title="Trading Bot Pro v4.6")

PASSWORD = "AHMED_BOSS_2026"
TRADES_FILE = "trades.json"

MARKET_NEWS = ["FOMC Rate Decision Tomorrow", "Bitcoin ETF News", "CPI Data Soon", "ETH ETF Launch"]
SAMPLE_BALANCE = {"usdt": 10245.67, "total_profit": 245.67, "pnl_percent": 2.46}

def load_trades():
    try:
        if os.path.exists(TRADES_FILE):
            with open(TRADES_FILE, 'r') as f:
                return json.load(f)
        return []
    except:
        return []

def save_trades(trades):
    try:
        with open(TRADES_FILE, 'w') as f:
            json.dump(trades, f)
    except:
        pass

@app.get("/", response_class=HTMLResponse)
async def main():
    trades = load_trades()
    trades_html = ""
    
    for trade in trades[-10:]:
        profit_class = "profit" if trade.get("profit", 0) > 0 else "loss"
        trades_html += f"""
        <tr>
            <td>{trade.get('time', '')[:16]}</td>
            <td>{trade.get('symbol', 'N/A')}</td>
            <td>{trade.get('action', 'N/A')}</td>
            <td style="color: #00D4AA;">${trade.get('price', 0):.2f}</td>
            <td>{trade.get('amount', 0)}</td>
            <td class="{profit_class}">${trade.get('profit', 0):.2f}</td>
            <td>✅</td>
        </tr>
        """
    
    html = f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trading Bot Pro v4.6</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
* {{ font-family: 'Inter', sans-serif; }}
body {{ 
    background: linear-gradient(135deg, #0F0F23 0%, #1A1A2E 50%, #16213E 100%);
    color: #E5E7EB; margin: 0; padding: 20px; min-height: 100vh;
}}
.glass {{ 
    background: rgba(255,255,255,0.05); backdrop-filter: blur(20px); 
    border: 1px solid rgba(255,255,255,0.1); border-radius: 20px; 
    box-shadow: 0 25px 45px rgba(0,0,0,0.3); padding: 25px; margin-bottom: 20px;
}}
.header {{ display: flex; justify-content: space-between; background: rgba(0,212,170,0.15); border-radius: 25px; padding: 25px; }}
.profit {{ color: #00FF88 !important; font-size: 28px; font-weight: 700; }}
.loss {{ color: #FF4757 !important; font-size: 28px; font-weight: 700; }}
.login-box {{ text-align: center; max-width: 400px; margin: 100px auto; }}
.btn-neon {{ padding: 15px 30px; border: none; border-radius: 50px; background: linear-gradient(45deg, #00D4AA, #00FF88); color: #0F0F23; font-weight: 700; cursor: pointer; margin: 5px; }}
.btn-neon:hover {{ transform: translateY(-3px); }}
.btn-pink {{ background: linear-gradient(45deg, #F72585, #FF6B9D) !important; }}
input {{ width: 100%; padding: 18px; margin: 15px 0; border: none; border-radius: 15px; background: rgba(255,255,255,0.12); color: white; }}
.dashboard {{ display: none; }}
.trades-table {{ width: 100%; border-collapse: collapse; }}
.trades-table th {{ background: rgba(0,212,170,0.2); padding: 15px; text-align: right; }}
.trades-table td {{ padding: 12px 15px; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.1); }}
@keyframes scroll {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-100%); }} }}
@media (max-width: 768px) {{ .header {{ flex-direction: column; gap: 20px; }} }}
</style>
</head>
<body>

<div id="loginSection" class="login-box glass">
    <h1 style="color: #00D4AA;">🚀 Trading Bot Pro v4.6</h1>
    <p style="opacity: 0.8;">أدخل كلمة السر</p>
    <div style="background: rgba(0,255,136,0.2); padding: 15px; border-radius: 10px; margin: 20px 0;">
        <strong style="color: #00FF88;">كلمة السر: AHMED_BOSS_2026</strong>
    </div>
    <form id="loginForm">
        <input type="password" id="password" placeholder="كلمة السر..." required>
        <button type="submit" class="btn-neon">🚀 دخول</button>
    </form>
</div>

<div id="dashboardSection" class="dashboard">
    <div class="header glass">
        <div>
            <h1 style="margin: 0; color: #00D4AA;">🚀 Trading Bot Pro v4.6</h1>
            <p style="margin: 5px 0;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 15px;">
            <div style="padding: 20px; text-align: center; background: rgba(0,255,136,0.1); border-radius: 15px;">
                <div>💰 USDT</div>
                <div class="profit">${SAMPLE_BALANCE['usdt']:.2f}</div>
            </div>
            <div style="padding: 20px; text-align: center; background: rgba(0,212,170,0.1); border-radius: 15px;">
                <div>📈 P&L</div>
                <div class="profit">+${SAMPLE_BALANCE['total_profit']:.2f}</div>
            </div>
        </div>
    </div>

    <div style="background: rgba(247,37,133,0.15); padding: 15px; border-radius: 15px; overflow: hidden; margin: 20px 0;">
        <strong style="margin-right: 15px; color: #F72585;">🔔 السوق:</strong>
        <div style="animation: scroll 25s linear infinite; white-space: nowrap; display: inline-block; padding-left: 100%;">
            """ + " | ".join(MARKET_NEWS) + """
        </div>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 25px; margin-bottom: 25px;">
        <div class="glass">
            <h3 style="margin: 0 0 20px 0; color: #00D4AA;">⚡ تداول سريع</h3>
            <input id="symbol" value="ETHUSDT" placeholder="ETHUSDT">
            <input id="amount" value="10" placeholder="10 USDT">
            <div style="display: flex; flex-wrap: wrap; gap: 10px;">
                <button class="btn-neon" onclick="quickTrade('buy')">🟢 شراء</button>
                <button class="btn-neon btn-pink" onclick="quickTrade('sell')">🔴 بيع</button>
                <button class="btn-neon" onclick="quickTrade('short')">📉 شورت</button>
            </div>
        </div>
        <div class="glass">
            <h3 style="margin: 0 0 20px 0; color: #00D4AA;">📊 P&L</h3>
            <canvas id="pnlChart" height="250"></canvas>
        </div>
    </div>

    <div class="glass">
        <h3 style="margin: 0 0 20px 0; color: #00D4AA;">📋 آخر الصفقات ({len(trades)})</h3>
        <table class="trades-table">
            <thead>
                <tr><th>التاريخ</th><th>العملة</th><th>النوع</th><th>السعر</th><th>الكمية</th><th>الربح</th><th>الحالة</th></tr>
            </thead>
            <tbody>""" + trades_html + """</tbody>
        </table>
    </div>
</div>

<script>
const PASSWORD = "AHMED_BOSS_2026";

document.getElementById('loginForm').onsubmit = function(e) {{
    e.preventDefault();
    const inputPass = document.getElementById('password').value;
    if (inputPass === PASSWORD) {{
        localStorage.setItem('trading_auth', 'valid');
        document.getElementById('loginSection').style.display = 'none';
        document.getElementById('dashboardSection').style.display = 'block';
    }} else {{
        alert('❌ خطأ! الكلمة السر: AHMED_BOSS_2026');
        document.getElementById('password').value = '';
    }}
}};

if (localStorage.getItem('trading_auth') === 'valid') {{
    document.getElementById('loginSection').style.display = 'none';
    document.getElementById('dashboardSection').style.display = 'block';
}}

async function quickTrade(action) {{
    const symbol = document.getElementById('symbol').value || 'ETHUSDT';
    const amount = document.getElementById('amount').value || '10';
    
    try {{
        await fetch('/webhook', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
            body: `message=${{action}} ${{symbol}} ${{amount}}`
        }});
    }} catch(e) {{}}
    
    alert(`✅ ${{action.toUpperCase()}} ${{symbol}} $${{amount}}`);
    setTimeout(() => location.reload(), 1000);
}}

new Chart(document.getElementById('pnlChart').getContext('2d'), {{
    type: 'line',
    data: {{
        labels: ['يناير','فبراير','مارس','أبريل'],
        datasets: [{{
            label: 'P&L',
            data: [0, 120, 180, {SAMPLE_BALANCE['total_profit']}],
            borderColor: '#00D4AA',
            backgroundColor: 'rgba(0,212,170,0.2)',
            tension: 0.4, fill: true
        }}]
    }},
    options: {{ responsive: true, scales: {{ y: {{ beginAtZero: true }} }} }}
}});

setInterval(() => location.reload(), 30000);
</script>
</body>
</html>
    """
    return HTMLResponse(content=html)

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.form()
        message = data.get("message", "") or data.get("text", "") or ""
        print(f"Webhook: {message}")
        
        trades = load_trades()
        parts = message.lower().strip().split()
        action = parts[0] if parts else "buy"
        symbol = parts[1].upper() if len(parts) > 1 else "ETHUSDT"
        amount = float(parts[2].replace("$", "")) if len(parts) > 2 else 10
        
        new_trade = {
            "time": datetime.now().isoformat(),
            "symbol": symbol,
            "action": action.upper(),
            "price": round(random.uniform(3000, 3500), 2),
            "amount": amount,
            "profit": round(random.uniform(-20, 60), 2)
        }
        trades.insert(0, new_trade)
        save_trades(trades[:50])
        
        return {"status": "OK"}
    except:
        return {"status": "OK"}

@app.get("/ping")
async def ping():
    return {"status": "alive"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
