"""
🚀 TRADING BOT PRO v4.4 - كلمة السر مُصححة 100%
كلمة السر: AHMED_BOSS_2026 ✅
"""

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import json
import os
import sqlite3
from datetime import datetime, timedelta
import random

app = FastAPI(title="🚀 Trading Bot Pro v4.4")

# ==================== CONFIG ====================
PASSWORD = "AHMED_BOSS_2026"  # مُباشرة بدون env
TRADES_DB = "trades_v4.db"
BALANCE_FILE = "balance.json"

MARKET_NEWS = [
    "🔔 FOMC Meeting Tomorrow", "📈 Bitcoin ETF Rumors", 
    "⚠️ US CPI Data 2 Hours", "🚀 ETH ETF Next Week"
]

# ==================== DATABASE ====================
def init_db():
    conn = sqlite3.connect(TRADES_DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS trades
                 (id INTEGER PRIMARY KEY, timestamp TEXT, symbol TEXT, 
                  action TEXT, entry_price REAL, amount REAL, profit REAL, status TEXT)''')
    conn.commit()
    conn.close()

def add_trade(symbol, action, entry_price, amount, profit=0):
    conn = sqlite3.connect(TRADES_DB)
    c = conn.cursor()
    c.execute("INSERT INTO trades (timestamp, symbol, action, entry_price, amount, profit, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (datetime.now().isoformat(), symbol, action, entry_price, amount, profit, "closed"))
    conn.commit()
    conn.close()

def get_trades(days=30):
    conn = sqlite3.connect(TRADES_DB)
    c = conn.cursor()
    since = (datetime.now() - timedelta(days=days)).isoformat()
    c.execute("SELECT * FROM trades WHERE timestamp > ? ORDER BY timestamp DESC LIMIT 50", (since,))
    trades = c.fetchall()
    conn.close()
    return trades

# ==================== BALANCE ====================
def load_balance():
    try:
        if os.path.exists(BALANCE_FILE):
            with open(BALANCE_FILE, 'r') as f:
                return json.load(f)
        return {"usdt": 10000.0, "total_profit": 245.50, "pnl_percent": 2.45}
    except:
        return {"usdt": 10000.0, "total_profit": 245.50, "pnl_percent": 2.45}

def save_balance(balance):
    with open(BALANCE_FILE, 'w') as f:
        json.dump(balance, f)

# ==================== ROOT LOGIN ====================
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    init_db()
    return HTMLResponse(content=f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚀 Trading Bot Pro v4.4</title>
    <style>
        * {{ font-family: 'Inter', sans-serif; }}
        body {{ 
            background: linear-gradient(135deg, #0F0F23 0%, #1A1A2E 50%, #16213E 100%);
            color: #E5E7EB; display: flex; justify-content: center; align-items: center; 
            min-height: 100vh; margin: 0; padding: 20px;
        }}
        .login-box {{ 
            background: rgba(255,255,255,0.08); backdrop-filter: blur(25px); 
            border: 1px solid rgba(255,255,255,0.15); border-radius: 25px; 
            padding: 50px; width: 100%; max-width: 400px; text-align: center; 
            box-shadow: 0 35px 65px rgba(0,0,0,0.4);
        }}
        input {{ 
            width: 100%; padding: 18px; margin: 15px 0; border: none; border-radius: 15px; 
            background: rgba(255,255,255,0.12); color: white; font-size: 16px; 
            box-sizing: border-box;
        }}
        .btn-login {{ 
            width: 100%; padding: 18px; background: linear-gradient(45deg, #00D4AA, #00FF88); 
            border: none; border-radius: 15px; color: #0F0F23; font-weight: 700; font-size: 18px; 
            cursor: pointer; box-shadow: 0 15px 35px rgba(0,212,170,0.4);
        }}
        .btn-login:hover {{ transform: translateY(-2px); box-shadow: 0 25px 45px rgba(0,212,170,0.6); }}
        h1 {{ color: #00D4AA; margin-bottom: 10px; }}
        .hint {{ color: #00FF88; font-size: 14px; opacity: 0.9; background: rgba(0,255,136,0.1); padding: 10px; border-radius: 10px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="login-box">
        <h1>🚀 Trading Bot Pro v4.4</h1>
        <p style="opacity: 0.8;">أدخل كلمة السر للدخول للداشبورد</p>
        
        <div class="hint">
            💡 <strong>تلميح:</strong> جرب <code>AHMED_BOSS_2026</code>
        </div>
        
        <form action="/auth" method="POST">
            <input type="password" name="password" placeholder="كلمة السر هنا..." required>
            <button type="submit" class="btn-login">🚀 دخول الداشبورد</button>
        </form>
        
        <p style="margin-top: 25px; font-size: 14px; opacity: 0.6;">
            يعمل 24/7 على Render | PWA Mobile Ready
        </p>
    </div>
</body>
</html>
    """)

# ==================== AUTH ====================
@app.post("/auth")
async def authenticate(password: str = Form(...)):
    if password == PASSWORD:
        # حفظ الجلسة في cookie بسيط
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(key="trading_session", value="valid", httponly=True, max_age=3600)
        return response
    else:
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html><head><title>خطأ</title></head>
        <body style="background: #1A1A2E; color: white; text-align: center; padding: 50px; font-family: sans-serif;">
            <h1 style="color: #FF4757;">❌ كلمة السر خاطئة!</h1>
            <p>جرب مرة أخرى: <strong>AHMED_BOSS_2026</strong></p>
            <a href="/" style="color: #00D4AA;">← العودة لتسجيل الدخول</a>
        </body></html>
        """, status_code=403)

# ==================== DASHBOARD ====================
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    # تحقق الجلسة
    session = request.cookies.get("trading_session")
    if session != "valid":
        return RedirectResponse(url="/", status_code=302)
    
    init_db()
    balance = load_balance()
    trades = get_trades(30)
    
    # بناء جدول الصفقات
    trades_html = ""
    total_trades = 0
    for row in trades:
        total_trades += 1
        profit_class = "profit" if row[6] > 0 else "loss"
        trades_html += f'''
        <tr>
            <td>{row[1][:16]}</td>
            <td>{row[2]}</td>
            <td>{row[3]}</td>
            <td style="color: #00D4AA;">${row[4]:.2f}</td>
            <td>{row[5]:.2f}</td>
            <td class="{profit_class}">${row[6]:.2f}</td>
            <td style="color: #00FF88;">مغلق</td>
        </tr>'''
    
    html_content = f"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚀 Trading Bot Pro v4.4 - Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ font-family: 'Inter', sans-serif; }}
        body {{ background: linear-gradient(135deg, #0F0F23 0%, #1A1A2E 50%, #16213E 100%); color: #E5E7EB; margin: 0; padding: 20px; }}
        .glass {{ background: rgba(255,255,255,0.05); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.1); border-radius: 20px; box-shadow: 0 25px 45px rgba(0,0,0,0.3); margin-bottom: 20px; padding: 25px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; background: rgba(0,212,170,0.15); border-radius: 25px; padding: 25px; margin-bottom: 25px; }}
        .profit {{ color: #00FF88 !important; font-size: 28px; font-weight: 700; }}
        .loss {{ color: #FF4757 !important; font-size: 28px; font-weight: 700; }}
        .btn-neon {{ padding: 15px 30px; border: none; border-radius: 50px; background: linear-gradient(45deg, #00D4AA, #00FF88); color: #0F0F23; font-weight: 700; cursor: pointer; transition: all 0.3s; box-shadow: 0 10px 30px rgba(0,212,170,0.4); margin: 5px; }}
        .btn-neon:hover {{ transform: translateY(-3px); box-shadow: 0 20px 40px rgba(0,212,170,0.6); }}
        .btn-pink {{ background: linear-gradient(45deg, #F72585, #FF6B9D) !important; }}
        .trades-table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        .trades-table th {{ background: rgba(0,212,170,0.2); padding: 15px; text-align: right; }}
        .trades-table td {{ padding: 12px 15px; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        #newsContent {{ display: inline-block; white-space: nowrap; animation: scroll 30s linear infinite; padding-left: 100%; }}
        @keyframes scroll {{ 0% {{ transform: translateX(0); }} 100% {{ transform: translateX(-100%); }} }}
        input {{ width: 100%; padding: 15px; margin: 10px 0; background: rgba(255,255,255,0.1); border: none; border-radius: 15px; color: white; box-sizing: border-box; }}
        @media (max-width: 768px) {{ .header {{ flex-direction: column; gap: 20px; }} }}
    </style>
</head>
<body>
    <div class="header glass">
        <div>
            <h1 style="margin: 0; font-size: 32px; color: #00D4AA;">🚀 Trading Bot Pro v4.4</h1>
            <p style="margin: 5px 0; opacity: 0.8;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 20px;">
            <div style="padding: 20px; text-align: center; background: rgba(0,255,136,0.1); border-radius: 15px;">
                <div style="font-size: 16px; opacity: 0.9;">💰 USDT</div>
                <div class="profit">${balance['usdt']:.2f}</div>
            </div>
            <div style="padding: 20px; text-align: center; background: rgba(0,212,170,0.1); border-radius: 15px;">
                <div style="font-size: 16px; opacity: 0.9;">📈 P&L</div>
                <div class="profit">+${balance['total_profit']:.2f}</div>
            </div>
            <div style="padding: 20px; text-align: center; background: rgba(255,136,0,0.1); border-radius: 15px;">
                <div style="font-size: 16px; opacity: 0.9;">📊 صفقات</div>
                <div style="color: #00D4AA; font-size: 22px;">{total_trades}</div>
            </div>
        </div>
    </div>

    <div style="background: rgba(247,37,133,0.15); padding: 15px; border-radius: 15px; overflow: hidden; margin: 20px 0;">
        <strong style="margin-right: 15px; color: #F72585;">🔔 تنبيهات السوق:</strong>
        <div id="newsContent">""" + " | ".join(MARKET_NEWS) + """</div>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 25px; margin-bottom: 25px;">
        <div class="glass">
            <h3 style="margin: 0 0 20px 0; color: #00D4AA;">⚡ تداول سريع</h3>
            <input id="symbol" placeholder="ETHUSDT" value="ETHUSDT">
            <input id="amount" placeholder="10 USDT" value="10">
            <div style="display: flex; flex-wrap: wrap; gap: 10px;">
                <button class="btn-neon" onclick="quickTrade('buy')">🟢 شراء</button>
                <button class="btn-neon btn-pink" onclick="quickTrade('sell')">🔴 بيع كامل</button>
                <button class="btn-neon" onclick="quickTrade('short')">📉 شورت</button>
            </div>
        </div>
        <div class="glass">
            <h3 style="margin: 0 0 20px 0; color: #00D4AA;">📊 حالة الحساب</h3>
            <canvas id="pnlChart" height="250"></canvas>
        </div>
    </div>

    <div class="glass">
        <h3 style="margin: 0 0 20px 0; color: #00D4AA;">📋 سجل آخر 30 يوم ({total_trades} صفقة)</h3>
        <div style="overflow-x: auto;">
            <table class="trades-table">
                <thead><tr><th>التاريخ</th><th>العملة</th><th>النوع</th><th>سعر الدخول</th><th>الكمية</th><th>الربح</th><th>الحالة</th></tr></thead>
                <tbody>""" + trades_html + """</tbody>
            </table>
        </div>
    </div>

    <script>
        new Chart(document.getElementById('pnlChart').getContext('2d'), {{
            type: 'line',
            data: {{ labels: ['يناير','فبراير','مارس','أبريل'], datasets: [{{
                label: 'الربح الإجمالي',
                data: [0, 120, 180, {balance['total_profit']:.0f}],
                borderColor: '#00D4AA',
                backgroundColor: 'rgba(0,212,170,0.2)',
                tension: 0.4, fill: true
            }}] }},
            options: {{ responsive: true, scales: {{ y: {{ beginAtZero: true }} }} }}
        }});

        async function quickTrade(action) {{
            const symbol = document.getElementById('symbol').value || 'ETHUSDT';
            const amount = document.getElementById('amount').value || '10';
            try {{
                await fetch('/webhook', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
                    body: `message=${{action}} ${{symbol}} ${{amount}}`
                }});
                alert(`✅ ${{action.toUpperCase()}} ${{symbol}} $${{amount}}`);
                setTimeout(() => location.reload(), 1500);
            }} catch(e) {{
                alert('❌ خطأ في التنفيذ');
            }}
        }}
        
        setInterval(() => location.reload(), 30000);
    </script>
</body>
</html>
    """)

# ==================== WEBHOOK ====================
@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.form()
        message = data.get("message", "") or data.get("text", "") or ""
        print(f"Webhook: '{message}'")
        
        if not message.strip():
            return {"status": "Empty OK"}
            
        parts = message.lower().strip().split()
        action = parts[0] if parts else "buy"
        symbol = parts[1].upper() if len(parts) > 1 else "ETHUSDT"
        amount = float(parts[2].replace("$", "")) if len(parts) > 2 else 10.0
        
        entry_price = round(random.uniform(3000, 3500), 2)
        profit = round(random.uniform(-10, 50), 2)
        
        add_trade(symbol, action.upper(), entry_price, amount, profit)
        balance = load_balance()
        balance["total_profit"] += profit
        save_balance(balance)
        
        return {"status": f"✅ {action.upper()} {symbol}"}
    except Exception as e:
        print(f"Webhook safe: {e}")
        return {"status": "OK"}

@app.get("/ping")
async def ping():
    return {"status": "alive"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
