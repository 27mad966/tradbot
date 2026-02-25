from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
import json
import os
from datetime import datetime
import random

app = FastAPI(title="🚀 Trading Pro v3.1")

TRADES_FILE = "trades.json"
BALANCE_FILE = "balance.json"

def load_data():
    trades = []
    balance = {"usdt": 10000, "total_profit": 0}
    
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, 'r') as f:
                trades = json.load(f)
        except:
            pass
    
    if os.path.exists(BALANCE_FILE):
        try:
            with open(BALANCE_FILE, 'r') as f:
                balance = json.load(f)
        except:
            pass
    
    return trades, balance

def save_data(trades, balance):
    with open(TRADES_FILE, 'w') as f:
        json.dump(trades, f, indent=2)
    with open(BALANCE_FILE, 'w') as f:
        json.dump(balance, f, indent=2)

def calculate_stats(trades):
    total_profit = sum(t.get("profit", 0) for t in trades if t.get("profit"))
    closed_trades = [t for t in trades if t.get("status") == "CLOSED"]
    win_rate = (len([t for t in closed_trades if t.get("profit", 0) > 0]) / len(closed_trades) * 100) if closed_trades else 0
    
    return {
        "total_profit": total_profit,
        "win_rate": win_rate,
        "total_trades": len(trades),
        "open_trades": len([t for t in trades if t["status"] == "OPEN"]),
        "closed_trades": len(closed_trades)
    }

# Webhook محسّن
@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.form() or await request.json()
        message = str(data).lower()
        print(f"🔔 Webhook: {data}")
        
        trades, balance_data = load_data()
        current_price = round(random.uniform(3000, 3500), 2)
        
        # شراء
        if "buy" in message:
            parts = str(data).split()
            symbol = next((p.upper() for p in parts if "USDT" in p), "ETHUSDT")
            amount = next((float(p) for p in parts if p.replace('.','').isdigit()), 10)
            
            trade = {
                "id": len(trades) + 1,
                "type": "شراء",
                "symbol": symbol,
                "amount": round(amount / current_price, 6),
                "entry_price": current_price,
                "total_usdt": amount,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "مفتوحة"
            }
            trades.append(trade)
            balance_data["usdt"] -= amount
            save_data(trades, balance_data)
            print(f"✅ شراء: {symbol} ${amount}")
            return {"status": "شراء ناجح", "trade": trade}
        
        # بيع
        elif "sell" in message:
            open_trades = [t for t in trades if t["status"] == "مفتوحة"]
            if open_trades:
                buy_trade = open_trades[-1]  # آخر صفقة مفتوحة
                exit_price = round(random.uniform(3100, 3800), 2)
                profit = round((exit_price - buy_trade["entry_price"]) * buy_trade["amount"], 2)
                
                buy_trade.update({
                    "status": "مغلقة",
                    "exit_price": exit_price,
                    "profit": profit,
                    "exit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                
                balance_data["usdt"] += (buy_trade["total_usdt"] + profit)
                balance_data["total_profit"] += profit
                save_data(trades, balance_data)
                
                print(f"✅ بيع: ${profit} ربح")
                return {"status": "بيع ناجح", "profit": profit}
        
        # شورت
        elif "short" in message:
            parts = str(data).split()
            symbol = next((p.upper() for p in parts if "USDT" in p), "ETHUSDT")
            amount = next((float(p) for p in parts if p.replace('.','').isdigit()), 10)
            
            trade = {
                "id": len(trades) + 1,
                "type": "شورت",
                "symbol": symbol,
                "amount": round(amount / current_price, 6),
                "entry_price": current_price,
                "total_usdt": amount,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "مفتوحة"
            }
            trades.append(trade)
            balance_data["usdt"] -= amount
            save_data(trades, balance_data)
            return {"status": "شورت ناجح", "trade": trade}
        
        return {"status": "تم الاستلام"}
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return {"error": str(e)}

# Dashboard احترافي مُحسّن
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    trades, balance_data = load_data()
    stats = calculate_stats(trades)
    
    html_content = f"""
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚀 Trading Bot Pro v3.1</title>
    <style>
        *{{margin:0;padding:0;box-sizing:border-box;}}
        body{{font-family:'Segoe UI',Tahoma,sans-serif;background:linear-gradient(135deg,#0c0c1a 0%,#1a1a2e 100%);color:#fff;padding:20px;}}
        .container{{max-width:1400px;margin:0 auto;}}
        .header{{text-align:center;margin-bottom:30px;}}
        .header h1{{font-size:2.8em;color:#00ff88;margin-bottom:10px;}}
        .stats-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px;margin-bottom:30px;}}
        .stat-card{{background:rgba(255,255,255,0.1);padding:25px;border-radius:20px;text-align:center;border:1px solid rgba(255,255,255,0.2);}}
        .profit-big{{font-size:3em;font-weight:bold;color:#00ff88;text-shadow:0 0 20px rgba(0,255,136,0.5);}}
        .loss-big{{font-size:3em;font-weight:bold;color:#ff4444;}}
        .balance-card{{grid-column:1/-1;background:linear-gradient(135deg,#00ff88,#00cc6a);color:#000;padding:30px;border-radius:20px;text-align:center;}}
        .terminal{{background:rgba(255,255,255,0.1);padding:25px;border-radius:20px;margin:30px 0;}}
        .terminal-inputs{{display:flex;gap:15px;margin-bottom:20px;flex-wrap:wrap;}}
        .terminal-inputs input{{flex:1;padding:15px;border-radius:10px;border:1px solid rgba(255,255,255,0.3);background:rgba(255,255,255,0.1);color:#fff;min-width:120px;}}
        .btn{{padding:15px 25px;border:none;border-radius:10px;font-weight:bold;cursor:pointer;font-size:1.1em;transition:all 0.3s;}}
        .btn-buy{{background:linear-gradient(135deg,#00ff88,#00cc6a);color:#000;}}
        .btn-sell{{background:linear-gradient(135deg,#ff4444,#cc0000);color:#fff;}}
        .btn-short{{background:linear-gradient(135deg,#ffaa00,#ff8800);color:#000;}}
        .trades-table{{background:rgba(255,255,255,0.1);border-radius:20px;overflow:hidden;}}
        table{{width:100%;border-collapse:collapse;}}
        th{{background:linear-gradient(135deg,#00ff88,#00cc6a);color:#000;padding:15px;font-weight:600;text-align:right;}}
        td{{padding:15px;border-bottom:1px solid rgba(255,255,255,0.1);}}
        tr:hover{{background:rgba(255,255,255,0.1);}}
        .profit-cell.green{{color:#00ff88;font-weight:bold;}}
        .profit-cell.red{{color:#ff4444;font-weight:bold;}}
        @media(max-width:768px){{.stats-grid{{grid-template-columns:1fr;}}.terminal-inputs{{flex-direction:column;}}}}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Trading Bot Pro v3.1</h1>
            <p>نظام تداول احترافي | Live Updates | كامل المعلومات</p>
        </div>
        
        <div class="balance-card">
            <h2>💰 رصيد الحساب</h2>
            <div style="font-size:2.5em;font-weight:bold;">${balance_data['usdt']:.2f} USDT</div>
            <div style="font-size:1.2em;margin-top:10px;">إجمالي الأرباح: <span class="{'profit-big' if balance_data['total_profit']>=0 else 'loss-big'}">${balance_data['total_profit']:.2f}</span></div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div style="font-size:2.5em;">{stats['total_trades']}</div>
                <div style="color:#aaa;">إجمالي الصفقات</div>
            </div>
            <div class="stat-card">
                <div style="font-size:2.5em;">{stats['open_trades']}</div>
                <div style="color:#aaa;">صفقات مفتوحة</div>
            </div>
            <div class="stat-card">
                <div style="font-size:2.5em;">{stats['closed_trades']}</div>
                <div style="color:#aaa;">صفقات مغلقة</div>
            </div>
            <div class="stat-card">
                <div style="font-size:2.5em;">{stats['win_rate']:.1f}%</div>
                <div style="color:#aaa;">نسبة النجاح</div>
            </div>
        </div>
        
        <div class="terminal">
            <h3 style="color:#00ff88;margin-bottom:20px;">⚡ لوحة التحكم السريعة</h3>
            <div class="terminal-inputs">
                <input id="symbol" value="ETHUSDT" placeholder="الزوج">
                <input id="amount" type="number" value="10" placeholder="المبلغ USDT">
                <button class="btn btn-buy" onclick="quickTrade('buy')">شراء</button>
                <button class="btn btn-sell" onclick="quickTrade('sell')">بيع</button>
                <button class="btn btn-short" onclick="quickTrade('short')">شورت</button>
            </div>
        </div>
        
        <div class="trades-table">
            <table>
                <thead>
                    <tr>
                        <th>النوع</th><th>الزوج</th><th>سعر الدخول</th><th>الكمية</th><th>سعر الخروج</th><th>الربح</th><th>الحالة</th><th>التاريخ</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    recent_trades = trades[-20:]
    for trade in recent_trades:
        profit_class = "profit-cell green" if trade.get("profit", 0) > 0 else "profit-cell red"
        profit_display = f"${trade.get('profit', 0):.2f}" if trade.get("profit") else "-"
        exit_price = trade.get("exit_price", "-")
        
        html_content += f"""
        <tr>
            <td style="color:{'#00ff88' if trade['type']=='شراء' else '#ffaa00' if trade['type']=='شورت' else '#ff4444'}">{trade['type']}</td>
            <td><strong>{trade['symbol']}</strong></td>
            <td style="color:#00ff88;">${trade['entry_price']:.4f}</td>
            <td>{trade['amount']:.6f}</td>
            <td style="color:#aaa;">{exit_price}</td>
            <td class="{profit_class}">{profit_display}</td>
            <td style="font-weight:bold;color:{'#00ff88' if trade['status']=='مغلقة' else '#ffaa00'}">{trade['status']}</td>
            <td style="font-size:0.9em;color:#aaa;">{trade['timestamp']}</td>
        </tr>
        """
    
    html_content += """
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        async function quickTrade(type) {{
            const symbol = document.getElementById('symbol').value;
            const amount = document.getElementById('amount').value;
            const message = `${{type}} ${{symbol}} ${{amount}}`;
            
            try {{
                const response = await fetch('/webhook', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{message: message}})
                }});
                alert(`✅ ${{type === 'buy' ? 'شراء' : type === 'sell' ? 'بيع' : 'شورت'}} ناجح!`);
                location.reload();
            }} catch (e) {{
                alert('❌ خطأ في التنفيذ');
            }}
        }}
        
        // Auto refresh كل 10 ثواني
        setTimeout(() => location.reload(), 10000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
