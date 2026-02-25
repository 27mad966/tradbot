from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import json, os, random
from datetime import datetime, timedelta

app = FastAPI()

TRADES_FILE = "trades.json"
PORTFOLIO_FILE = "portfolio.json"

def load_json(file, default={}):
    try: return json.load(open(file)) if os.path.exists(file) else default
    except: return default

def save_json(file, data): json.dump(data, open(file, 'w'), indent=2)

def load_trades(): 
    trades = load_json(TRADES_FILE, [])
    return [t for t in trades[-100:] if 'time' in t]

def save_trade(trade):
    trades = load_trades()
    trades.append(trade)
    save_json(TRADES_FILE, trades)

def update_portfolio(symbol, action, qty, price):
    pf = load_json(PORTFOLIO_FILE, {"USDT": 10000, "positions": {}})
    if action == "BUY":
        cost = qty * price
        if pf["USDT"] >= cost:
            pf["USDT"] -= cost
            pf["positions"][symbol] = pf["positions"].get(symbol, 0) + qty
    elif action == "SELL" and symbol in pf["positions"]:
        pf["positions"][symbol] = max(0, pf["positions"][symbol] - qty)
        pf["USDT"] += qty * price
    pf["positions"] = {k:v for k,v in pf["positions"].items() if v>0}
    save_json(PORTFOLIO_FILE, pf)
    return pf

@app.get("/api/portfolio")
async def api_portfolio():
    pf = load_json(PORTFOLIO_FILE, {"USDT": 10000, "positions": {}})
    total = pf["USDT"]
    for sym, qty in pf["positions"].items(): total += qty * 100
    return {"cash": pf["USDT"], "total": total, "positions": pf["positions"]}

@app.get("/api/trades")
async def api_trades():
    trades = load_trades()
    profit = sum(t.get('profit', 0) for t in trades)
    return {"trades": trades[-15:], "profit": profit, "count": len(trades)}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    sym, act, price, qty = data.get("symbol", "BTCUSDT"), data.get("action", "BUY"), data.get("price", 100), data.get("amount", 10)
    
    pf = update_portfolio(sym, act, qty, price)
    profit = qty * price * random.uniform(-0.05, 0.1)
    
    trade = {"time": datetime.utcnow().isoformat(), "symbol": sym, "action": act, 
             "price": price, "qty": qty, "profit": profit}
    save_trade(trade)
    return {"status": "OK", "trade": trade}

@app.get("/ping")
async def ping(): return {"alive": True}

@app.get("/")
async def dashboard():
    trades = load_trades()
    portfolio = load_json(PORTFOLIO_FILE)
    
    html = f"""
<!DOCTYPE html><html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<title>Trading Bot v7.1</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}body{{font-family:Arial;background:#1a1a2e;color:white;padding:20px}}
.container{{max-width:1400px;margin:0 auto}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.card{{background:#0f0f23;border-radius:10px;padding:25px;border:1px solid #333}}
h3{{color:#00D4AA;margin-bottom:15px}}.metric{{text-align:center;padding:15px;background:#1a1a2e;border-radius:8px;margin:5px 0}}
.metric-value{{font-size:1.5em;font-weight:bold}}.profit{{color:#00D4AA}}.loss{{color:#ff4444}}
table{{width:100%;border-collapse:collapse;font-size:0.85em}}th,td{{padding:10px 6px;text-align:right;border-bottom:1px solid #333}}
th{{background:#16213e}}.symbol{{color:#00D4AA;font-weight:bold}}button{{background:#00D4AA;color:white;border:none;padding:10px 20px;border-radius:6px;cursor:pointer;margin:5px}}button:hover{{background:#00A085}}
@media(max-width:768px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body>
<div class="container">
<div class="card"><h3>💰 المحفظة</h3>
<div>إجمالي: $<span id=total>{portfolio.get("USDT",10000)+sum(portfolio.get("positions",{})).values()*100:.0f}</span></div>
<div>نقد USDT: $<span id=cash>{portfolio.get("USDT",10000):.0f}</span></div></div>
<div class="card"><h3>📊 الإحصائيات</h3>
<div>الصفقات: <span id=trades>0</span> | ربح: $<span id=profit>0</span></div></div>
<div class="card"><h3>📈 آخر الصفقات</h3>
<button onclick=testTrade()>اختبار</button><button onclick=location.reload()>تحديث</button>
<table id=table><tr><th>وقت</th><th>رمز</th><th>نوع</th><th>سعر</th><th>كمية</th><th>ربح</th></tr>"""
    
    for t in trades[-10:]:
        html += f"<tr><td>{t.get('time','N/A')[:16]}</td><td class=symbol>{t.get('symbol','N/A')}</td><td>{t.get('action','N/A')}</td><td>${t.get('price',0):.2f}</td><td>{t.get('qty',0):.2f}</td><td class={'profit' if t.get('profit',0)>0 else 'loss'}>${t.get('profit',0):.2f}</td></tr>"
    
    html += """</table></div></div>
<script>
async function update(){
try{
const pf=await(await fetch('/api/portfolio')).json();
const tr=await(await fetch('/api/trades')).json();
document.getElementById('total').textContent=pf.total.toLocaleString();
document.getElementById('cash').textContent=pf.cash.toLocaleString();
document.getElementById('trades').textContent=tr.count;
document.getElementById('profit').textContent=tr.profit.toLocaleString();
document.getElementById('table').querySelector('tbody').innerHTML=tr.trades.map(t=>`<tr><td>${t.time.slice(0,16)}</td><td class=symbol>${t.symbol}</td><td>${t.action}</td><td>$${t.price.toFixed(2)}</td><td>${t.qty.toFixed(2)}</td><td class=${t.profit>0?'profit':'loss'}>$${t.profit.toFixed(2)}</td></tr>`).join('');
}catch(e){console.log(e)}}
async function testTrade(){await fetch('/webhook',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({symbol:['BTCUSDT','ETHUSDT'][Math.random()*2|0],action:Math.random()>0.5?'BUY':'SELL',price:100,amount:10})});update()}
update();setInterval(update,3000);
</script></body></html>"""
    
    return HTMLResponse(html)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
