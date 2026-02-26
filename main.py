import os, asyncio, ccxt, uvicorn
from datetime import datetime
from collections import deque
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Signal(BaseModel):
    pair: str
    direction: str

INITIAL_BALANCE = 10000.0
settings = {
    "buy_mode": "fixed",
    "buy_value": 100.0,
    "sell_mode": "percent",
    "sell_value": 1.0,
    "active": True
}

active_connections: list[WebSocket] = []

class TradingBot:
    def __init__(self):
        self.ex = ccxt.binance({
            'apiKey': os.getenv("BINANCE_API_KEY", "").strip(),
            'secret': os.getenv("BINANCE_SECRET_KEY", "").strip(),
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
                'recvWindow': 15000,
                'defaultType': 'spot'
            }
        })
        self.ex.set_sandbox_mode(True)
        self.trades = deque(maxlen=100)
        self.buy_prices: dict[str, float] = {}  # لتتبع سعر الشراء لكل عملة

    async def get_balance(self):
        """جلب الرصيد الفعلي من Binance Testnet بشكل صحيح"""
        try:
            bal = self.ex.fetch_balance()
            usdt = float(bal['total'].get('USDT', 0.0))
            portfolio_value = usdt
            holdings = {}

            coins = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'MATIC']
            for c in coins:
                amt = float(bal['total'].get(c, 0.0))
                if amt > 0.0001:
                    try:
                        ticker = self.ex.fetch_ticker(f"{c}/USDT")
                        price = float(ticker['last'])
                        value = amt * price
                        portfolio_value += value
                        buy_price = self.buy_prices.get(c, price)
                        unrealized_pnl = (price - buy_price) * amt
                        holdings[c] = {
                            'amount': round(amt, 6),
                            'price': price,
                            'value': round(value, 2),
                            'unrealized_pnl': round(unrealized_pnl, 2)
                        }
                    except:
                        pass

            total_pnl = portfolio_value - INITIAL_BALANCE
            pnl_pct = round((total_pnl / INITIAL_BALANCE) * 100, 2)

            return {
                'usdt': round(usdt, 2),
                'total': round(portfolio_value, 2),
                'pnl': round(total_pnl, 2),
                'pnl_pct': pnl_pct,
                'holdings': holdings
            }
        except Exception as e:
            print(f"⚠️ خطأ في جلب الرصيد: {e}")
            return {'usdt': 0.0, 'total': INITIAL_BALANCE, 'pnl': 0.0, 'pnl_pct': 0.0, 'holdings': {}}

    def fix_pair(self, pair: str) -> str:
        pair = pair.upper().strip()
        pair = pair.replace("USDTUSDT", "USDT")
        if "/" in pair:
            return pair
        if pair.endswith("USDT"):
            return f"{pair[:-4]}/USDT"
        return f"{pair}/USDT"

    def execute(self, pair: str, side: str) -> dict:
        side = side.lower().strip()
        pair = self.fix_pair(pair)
        coin = pair.split('/')[0]
        print(f"📡 إشارة: {side} | {pair}")

        try:
            self.ex.load_markets()
            price = float(self.ex.fetch_ticker(pair)['last'])
            trade_pnl = 0.0

            if "buy" in side or "long" in side:
                bal = self.ex.fetch_balance()
                usdt = float(bal['total'].get('USDT', 0.0))
                val = settings["buy_value"] if settings["buy_mode"] == "fixed" else usdt * (settings["buy_value"] / 100)
                if val < 11: val = 11
                amt = float(self.ex.amount_to_precision(pair, val / price))
                self.ex.create_market_buy_order(pair, amt)
                self.buy_prices[coin] = price  # حفظ سعر الشراء
                msg = f"✅ شراء {amt} بـ {val:.1f}$"
                action_type = "buy"

            elif "sell" in side or "short" in side:
                bal = self.ex.fetch_balance()
                c_bal = float(bal['total'].get(coin, 0.0))
                if c_bal <= 0.0001:
                    raise Exception(f"لا يوجد رصيد من {coin}")
                sell_ratio = settings["sell_value"] if settings["sell_mode"] == "percent" else 1.0
                amt = float(self.ex.amount_to_precision(pair, c_bal * sell_ratio))
                self.ex.create_market_sell_order(pair, amt)
                # حساب الربح المحقق
                buy_price = self.buy_prices.get(coin, price)
                trade_pnl = round((price - buy_price) * amt, 2)
                if coin in self.buy_prices:
                    del self.buy_prices[coin]
                pnl_str = f"+{trade_pnl}$" if trade_pnl >= 0 else f"{trade_pnl}$"
                msg = f"✅ بيع {amt} | PnL: {pnl_str}"
                action_type = "sell"
            else:
                raise Exception(f"اتجاه غير معروف: {side}")

            res = {
                'id': int(datetime.now().timestamp() * 1000),
                'time': datetime.now().strftime("%H:%M:%S"),
                'date': datetime.now().strftime("%d/%m"),
                'pair': pair,
                'act': action_type,
                'price': price,
                'pnl': trade_pnl,
                'st': msg,
                'success': True
            }
            self.trades.appendleft(res)
            print(f"💰 {msg}")
            return res

        except Exception as e:
            err = str(e)
            print(f"❌ فشل: {err}")
            res = {
                'id': int(datetime.now().timestamp() * 1000),
                'time': datetime.now().strftime("%H:%M:%S"),
                'date': datetime.now().strftime("%d/%m"),
                'pair': pair,
                'act': side,
                'price': 0,
                'pnl': 0,
                'st': f"❌ {err[:80]}",
                'success': False
            }
            self.trades.appendleft(res)
            return res

    def liquidate_all(self):
        try:
            bal = self.ex.fetch_balance()
            for coin, amt in bal['total'].items():
                if coin == 'USDT' or float(amt) < 0.0001:
                    continue
                pair = f"{coin}/USDT"
                try:
                    self.ex.load_markets()
                    if pair in self.ex.markets:
                        self.ex.create_market_sell_order(pair, float(amt))
                        print(f"🔴 تصفية: {amt} {coin}")
                except Exception as e:
                    print(f"⚠️ فشل {coin}: {e}")
        except Exception as e:
            print(f"❌ خطأ في التصفية: {e}")


bot = TradingBot()


async def broadcast(data: dict):
    disconnected = []
    for ws in active_connections:
        try:
            await ws.send_json(data)
        except:
            disconnected.append(ws)
    for ws in disconnected:
        if ws in active_connections:
            active_connections.remove(ws)


HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SOVEREIGN V5</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=Tajawal:wght@300;400;700;900&display=swap" rel="stylesheet">
<style>
:root{--bg:#060810;--surface:#0d1117;--border:rgba(255,255,255,0.06);--gold:#f0b429;--gold-dim:rgba(240,180,41,0.12);--green:#00e676;--green-dim:rgba(0,230,118,0.1);--red:#ff4757;--red-dim:rgba(255,71,87,0.1);--blue:#00b4d8;--text:#e2e8f0;--muted:#4a5568;--mono:'IBM Plex Mono',monospace;--ar:'Tajawal',sans-serif}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:var(--ar);min-height:100vh;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(240,180,41,0.025) 1px,transparent 1px),linear-gradient(90deg,rgba(240,180,41,0.025) 1px,transparent 1px);background-size:48px 48px;pointer-events:none;z-index:0}
.wrap{max-width:1200px;margin:0 auto;padding:24px;position:relative;z-index:1}

.header{display:flex;align-items:center;justify-content:space-between;padding:20px 28px;background:var(--surface);border:1px solid var(--border);border-radius:16px;margin-bottom:16px;position:relative;overflow:hidden}
.header::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,var(--gold),transparent)}
.logo{font-family:var(--mono);font-size:20px;font-weight:700;color:var(--gold);letter-spacing:3px;text-shadow:0 0 30px rgba(240,180,41,0.4)}
.logo-sub{color:var(--muted);font-size:10px;letter-spacing:2px;display:block;margin-top:3px}
.status{display:flex;align-items:center;gap:8px;padding:8px 16px;border-radius:20px;font-size:11px;font-family:var(--mono);font-weight:600;border:1px solid;transition:all .3s}
.status.on{color:var(--green);border-color:rgba(0,230,118,.3);background:var(--green-dim)}
.status.off{color:var(--red);border-color:rgba(255,71,87,.3);background:var(--red-dim)}
.dot{width:7px;height:7px;border-radius:50%;background:currentColor;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

.ticker{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 20px;margin-bottom:16px;font-family:var(--mono);font-size:11px;color:var(--muted);display:flex;align-items:center;gap:12px}
.ticker-live{color:var(--gold);font-weight:700;background:var(--gold-dim);padding:3px 10px;border-radius:4px}

.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:16px}
@media(max-width:700px){.stats{grid-template-columns:repeat(2,1fr)}}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:20px;position:relative;overflow:hidden;transition:border-color .3s}
.card:hover{border-color:rgba(240,180,41,.2)}
.card-icon{position:absolute;top:14px;left:14px;font-size:26px;opacity:.1}
.card-label{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:10px;font-family:var(--mono)}
.card-value{font-family:var(--mono);font-size:22px;font-weight:700;line-height:1}
.card-sub{font-size:10px;color:var(--muted);margin-top:5px;font-family:var(--mono)}
.gold .card-value{color:var(--gold)}
.green .card-value{color:var(--green)}
.red .card-value{color:var(--red)}
.blue .card-value{color:var(--blue)}

.holdings{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px;min-height:0}
.chip{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:10px 16px;font-family:var(--mono);font-size:11px;display:flex;align-items:center;gap:8px}
.chip-coin{color:var(--gold);font-weight:700}
.pos{color:var(--green)}
.neg{color:var(--red)}
.muted{color:var(--muted)}

.section{background:var(--surface);border:1px solid var(--border);border-radius:16px;overflow:hidden}
.section-head{padding:16px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.section-title{font-size:11px;font-family:var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:2px}
.count-badge{font-family:var(--mono);font-size:11px;color:var(--gold);background:var(--gold-dim);padding:4px 10px;border-radius:20px}
.liq{background:var(--red-dim);color:var(--red);border:1px solid rgba(255,71,87,.3);padding:7px 14px;border-radius:8px;font-family:var(--mono);font-size:10px;font-weight:700;cursor:pointer;transition:all .2s;letter-spacing:1px}
.liq:hover{background:rgba(255,71,87,.25)}

table{width:100%;border-collapse:collapse}
thead th{padding:11px 20px;font-size:9px;font-family:var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:1.5px;text-align:right;background:rgba(255,255,255,.02);border-bottom:1px solid var(--border)}
tbody tr{border-bottom:1px solid rgba(255,255,255,.03);transition:background .2s}
tbody tr:hover{background:rgba(255,255,255,.02)}
tbody tr.flash{animation:flash 1.2s ease-out}
@keyframes flash{0%{background:rgba(240,180,41,.18)}100%{background:transparent}}
td{padding:13px 20px;font-size:12px;text-align:right;vertical-align:middle}
.t-time{font-family:var(--mono);color:var(--muted);font-size:10px}
.t-pair{font-family:var(--mono);font-weight:700}
.t-price{font-family:var(--mono);color:var(--gold)}
.badge{display:inline-block;padding:3px 11px;border-radius:5px;font-family:var(--mono);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px}
.b-buy{background:var(--green-dim);color:var(--green);border:1px solid rgba(0,230,118,.2)}
.b-sell{background:var(--red-dim);color:var(--red);border:1px solid rgba(255,71,87,.2)}
.pnl{font-family:var(--mono);font-weight:700;font-size:12px}
.t-status{font-size:10px;color:var(--muted);max-width:180px}
.empty{padding:50px;text-align:center;color:var(--muted);font-family:var(--mono);font-size:12px}
.empty span{font-size:36px;display:block;margin-bottom:12px;opacity:.25}

::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
</style>
</head>
<body>
<div class="wrap">

  <div class="header">
    <div class="logo">SOVEREIGN<span class="logo-sub">AUTOMATED TRADING SYSTEM · V5.0 · TESTNET</span></div>
    <div id="sb" class="status off"><div class="dot"></div><span id="st">جاري الاتصال...</span></div>
  </div>

  <div class="ticker">
    <span class="ticker-live">⚡ LIVE</span>
    <span id="clock">--:--:--</span>
    <span style="flex:1"></span>
    <span>آخر تحديث:</span><span id="upd" style="color:var(--text)">--</span>
  </div>

  <div class="stats">
    <div class="card gold"><div class="card-icon">💰</div><div class="card-label">إجمالي المحفظة</div><div class="card-value" id="cTotal">--</div><div class="card-sub">USDT</div></div>
    <div class="card blue"><div class="card-icon">💵</div><div class="card-label">رصيد USDT الحر</div><div class="card-value" id="cUsdt">--</div><div class="card-sub">متاح للتداول</div></div>
    <div class="card blue" id="pnlCard"><div class="card-icon">📊</div><div class="card-label">صافي الربح / الخسارة</div><div class="card-value" id="cPnl">--</div><div class="card-sub" id="cPnlPct">--</div></div>
    <div class="card blue"><div class="card-icon">🔢</div><div class="card-label">إجمالي الصفقات</div><div class="card-value" id="cCount">0</div><div class="card-sub">منذ بدء التشغيل</div></div>
  </div>

  <div class="holdings" id="holdings"></div>

  <div class="section">
    <div class="section-head">
      <span class="section-title">سجل الصفقات</span>
      <div style="display:flex;gap:8px;align-items:center">
        <span class="count-badge" id="countBadge">0 صفقة</span>
        <button class="liq" onclick="liq()">⚠ تصفية الكل</button>
      </div>
    </div>
    <div style="overflow-x:auto">
      <table>
        <thead><tr>
          <th>التاريخ</th><th>الوقت</th><th>الزوج</th><th>النوع</th>
          <th>سعر التنفيذ</th><th>الربح / الخسارة</th><th>الحالة</th>
        </tr></thead>
        <tbody id="tb"><tr><td colspan="7"><div class="empty"><span>📡</span>في انتظار الإشارات الأولى...</div></td></tr></tbody>
      </table>
    </div>
  </div>
</div>

<script>
let delay = 2000, known = new Set();

function connect() {
  const ws = new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws');
  ws.onopen = () => { document.getElementById('sb').className='status on'; document.getElementById('st').textContent='متصل · LIVE'; delay=2000; };
  ws.onmessage = e => render(JSON.parse(e.data));
  ws.onclose = () => { document.getElementById('sb').className='status off'; document.getElementById('st').textContent='انقطع الاتصال...'; setTimeout(connect,delay); delay=Math.min(delay*1.5,30000); };
  ws.onerror = () => ws.close();
}

function fmt(n,d=2){ return Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}); }

function render(d) {
  const now = new Date();
  document.getElementById('clock').textContent = now.toLocaleTimeString('ar-SA');
  document.getElementById('upd').textContent = now.toLocaleTimeString('ar-SA');

  const b = d.balance;
  document.getElementById('cTotal').textContent = fmt(b.total);
  document.getElementById('cUsdt').textContent = fmt(b.usdt);

  const pc = document.getElementById('pnlCard');
  const pv = document.getElementById('cPnl');
  pv.textContent = (b.pnl>=0?'+':'')+fmt(b.pnl);
  document.getElementById('cPnlPct').textContent = (b.pnl>=0?'+':'')+b.pnl_pct+'%';
  pc.className = 'card '+(b.pnl>0?'green':b.pnl<0?'red':'blue');

  const n = d.trades.length;
  document.getElementById('cCount').textContent = n;
  document.getElementById('countBadge').textContent = n+' صفقة';

  // Holdings
  const h = b.holdings||{};
  document.getElementById('holdings').innerHTML = Object.entries(h).map(([c,v])=>`
    <div class="chip">
      <span class="chip-coin">${c}</span>
      <span class="muted">${v.amount}</span>
      <span class="muted">@</span>
      <span>${fmt(v.price,2)}</span>
      <span class="${v.unrealized_pnl>=0?'pos':'neg'}">${v.unrealized_pnl>=0?'+':''}${fmt(v.unrealized_pnl,2)}$</span>
    </div>`).join('');

  // Trades
  if(!d.trades.length){
    document.getElementById('tb').innerHTML='<tr><td colspan="7"><div class="empty"><span>📡</span>في انتظار الإشارات الأولى...</div></td></tr>';
    return;
  }
  document.getElementById('tb').innerHTML = d.trades.map(x=>{
    const isNew = !known.has(x.id); if(isNew) known.add(x.id);
    const isBuy = x.act==='buy'||x.act==='long';
    const hasPnl = (x.act==='sell'||x.act==='short') && x.pnl!==0;
    const pnlHtml = hasPnl
      ? `<span class="pnl ${x.pnl>0?'pos':'neg'}">${x.pnl>0?'+':''}${fmt(x.pnl,2)}$</span>`
      : `<span class="muted" style="font-family:var(--mono)">—</span>`;
    return `<tr class="${isNew?'flash':''}">
      <td class="t-time">${x.date||'--'}</td>
      <td class="t-time">${x.time}</td>
      <td class="t-pair">${x.pair}</td>
      <td><span class="badge ${isBuy?'b-buy':'b-sell'}">${isBuy?'شراء':'بيع'}</span></td>
      <td class="t-price">${x.price>0?fmt(x.price,4):'—'}</td>
      <td>${pnlHtml}</td>
      <td class="t-status">${x.st}</td>
    </tr>`;
  }).join('');
}

async function liq() {
  if(!confirm('هل أنت متأكد من تصفية جميع المراكز المفتوحة؟')) return;
  await fetch('/liquidate',{method:'POST'});
}

connect();
setInterval(()=>{
  const t=new Date();
  const el=document.getElementById('clock');
  if(el) el.textContent=t.toLocaleTimeString('ar-SA');
},1000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    active_connections.append(ws)
    print(f"🔌 اتصال جديد | إجمالي: {len(active_connections)}")
    try:
        bal = await bot.get_balance()
        await ws.send_json({"balance": bal, "trades": list(bot.trades)})
        while True:
            await asyncio.sleep(5)
            bal = await bot.get_balance()
            await ws.send_json({"balance": bal, "trades": list(bot.trades)})
    except:
        pass
    finally:
        if ws in active_connections:
            active_connections.remove(ws)
        print(f"🔌 انقطع | إجمالي: {len(active_connections)}")


@app.post("/webhook")
async def webhook(s: Signal):
    if not settings.get("active", True):
        return {"status": "inactive"}
    result = bot.execute(s.pair, s.direction)
    bal = await bot.get_balance()
    await broadcast({"balance": bal, "trades": list(bot.trades)})
    return result


@app.post("/liquidate")
async def liquidate():
    bot.liquidate_all()
    bal = await bot.get_balance()
    await broadcast({"balance": bal, "trades": list(bot.trades)})
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok", "trades": len(bot.trades), "connections": len(active_connections)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
