import os, asyncio, ccxt, uvicorn
from datetime import datetime
from collections import deque
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Signal(BaseModel):
    pair: str
    direction: str          # buy | sell | long_open | long_close | short_open | short_close
    reason: Optional[str] = None   # stop_loss | peak_exit | trailing_stop
    market: Optional[str] = None   # spot | futures (يمكن تحديده من TradingView)

# ==========================================
# الإعدادات الرئيسية
# ==========================================
INITIAL_BALANCE_SPOT    = 10000.0
INITIAL_BALANCE_FUTURES = 10000.0

settings = {
    # تحكم عام
    "active":          True,
    "emergency_stop":  False,

    # إعدادات Spot
    "spot_buy_mode":   "fixed",   # fixed | percent
    "spot_buy_value":  100.0,     # دولار أو نسبة %
    "spot_sell_ratio": 1.0,       # 1.0 = 100% من الرصيد

    # إعدادات Futures
    "futures_mode":    "fixed",   # fixed | percent
    "futures_value":   100.0,     # حجم المركز
    "leverage":        10,        # الرافعة المالية (قابلة للتعديل)
    "futures_enabled": True,      # تفعيل/تعطيل Futures بشكل مستقل
}

active_connections: list[WebSocket] = []

# ==========================================
# بوت Spot
# ==========================================
class SpotBot:
    def __init__(self):
        self.ex = ccxt.binance({
            'apiKey': os.getenv("BINANCE_API_KEY", "").strip(),
            'secret': os.getenv("BINANCE_SECRET_KEY", "").strip(),
            'enableRateLimit': True,
            'options': {'adjustForTimeDifference': True, 'recvWindow': 15000, 'defaultType': 'spot'}
        })
        self.ex.set_sandbox_mode(True)
        self.trades = deque(maxlen=100)
        self.buy_prices: dict[str, float] = {}

    async def get_balance(self):
        try:
            bal = self.ex.fetch_balance()
            usdt = float(bal['total'].get('USDT', 0.0))
            portfolio_value = usdt
            holdings = {}
            for c in ['BTC','ETH','SOL','BNB','XRP','ADA','DOGE','AVAX']:
                amt = float(bal['total'].get(c, 0.0))
                if amt > 0.0001:
                    try:
                        price = float(self.ex.fetch_ticker(f"{c}/USDT")['last'])
                        value = amt * price
                        portfolio_value += value
                        buy_p = self.buy_prices.get(c, price)
                        holdings[c] = {
                            'amount': round(amt, 6),
                            'price': price,
                            'value': round(value, 2),
                            'unrealized_pnl': round((price - buy_p) * amt, 2)
                        }
                    except: pass
            pnl = portfolio_value - INITIAL_BALANCE_SPOT
            return {
                'usdt': round(usdt, 2),
                'total': round(portfolio_value, 2),
                'pnl': round(pnl, 2),
                'pnl_pct': round((pnl / INITIAL_BALANCE_SPOT) * 100, 2),
                'holdings': holdings
            }
        except Exception as e:
            print(f"⚠️ Spot balance error: {e}")
            return {'usdt': 0.0, 'total': INITIAL_BALANCE_SPOT, 'pnl': 0.0, 'pnl_pct': 0.0, 'holdings': {}}

    def fix_pair(self, pair: str) -> str:
        pair = pair.upper().strip().replace("USDTUSDT","USDT")
        if "/" in pair: return pair
        if pair.endswith("USDT"): return f"{pair[:-4]}/USDT"
        return f"{pair}/USDT"

    def execute(self, pair: str, side: str, reason: str = "") -> dict:
        side = side.lower().strip()
        pair = self.fix_pair(pair)
        coin = pair.split('/')[0]
        print(f"📡 [SPOT] {side} | {pair} | reason: {reason}")
        try:
            self.ex.load_markets()
            price = float(self.ex.fetch_ticker(pair)['last'])
            trade_pnl = 0.0

            if side in ["buy", "long_open"]:
                bal = self.ex.fetch_balance()
                usdt = float(bal['total'].get('USDT', 0.0))
                val = settings["spot_buy_value"] if settings["spot_buy_mode"] == "fixed" else usdt * (settings["spot_buy_value"] / 100)
                if val < 11: val = 11
                amt = float(self.ex.amount_to_precision(pair, val / price))
                self.ex.create_market_buy_order(pair, amt)
                self.buy_prices[coin] = price
                msg = f"✅ شراء {amt} بـ {val:.1f}$"
                action_type = "buy"

            elif side in ["sell", "long_close"]:
                bal = self.ex.fetch_balance()
                c_bal = float(bal['total'].get(coin, 0.0))
                if c_bal <= 0.0001: raise Exception(f"لا يوجد رصيد من {coin}")
                amt = float(self.ex.amount_to_precision(pair, c_bal * settings["spot_sell_ratio"]))
                self.ex.create_market_sell_order(pair, amt)
                buy_p = self.buy_prices.get(coin, price)
                trade_pnl = round((price - buy_p) * amt, 2)
                if coin in self.buy_prices: del self.buy_prices[coin]
                pnl_str = f"+{trade_pnl}$" if trade_pnl >= 0 else f"{trade_pnl}$"
                reason_ar = {"stop_loss": "وقف خسارة", "peak_exit": "ذروة", "trailing_stop": "وقف متحرك"}.get(reason, "خروج")
                msg = f"✅ بيع [{reason_ar}] PnL: {pnl_str}"
                action_type = "sell"
            else:
                raise Exception(f"أمر غير معروف: {side}")

            res = {
                'id': int(datetime.now().timestamp() * 1000),
                'time': datetime.now().strftime("%H:%M:%S"),
                'date': datetime.now().strftime("%d/%m"),
                'market': 'SPOT',
                'pair': pair, 'act': action_type,
                'price': price, 'pnl': trade_pnl,
                'reason': reason, 'st': msg, 'success': True
            }
            self.trades.appendleft(res)
            return res
        except Exception as e:
            err = str(e)
            print(f"❌ [SPOT] {err}")
            res = {
                'id': int(datetime.now().timestamp() * 1000),
                'time': datetime.now().strftime("%H:%M:%S"),
                'date': datetime.now().strftime("%d/%m"),
                'market': 'SPOT', 'pair': pair, 'act': side,
                'price': 0, 'pnl': 0, 'reason': reason,
                'st': f"❌ {err[:80]}", 'success': False
            }
            self.trades.appendleft(res)
            return res

    def liquidate_all(self):
        try:
            bal = self.ex.fetch_balance()
            for coin, amt in bal['total'].items():
                if coin == 'USDT' or float(amt) < 0.0001: continue
                pair = f"{coin}/USDT"
                try:
                    self.ex.load_markets()
                    if pair in self.ex.markets:
                        self.ex.create_market_sell_order(pair, float(amt))
                        print(f"🔴 [SPOT] تصفية {amt} {coin}")
                except Exception as e:
                    print(f"⚠️ فشل {coin}: {e}")
        except Exception as e:
            print(f"❌ خطأ تصفية Spot: {e}")


# ==========================================
# بوت Futures
# ==========================================
class FuturesBot:
    def __init__(self):
        self.ex = ccxt.binance({
            'apiKey': os.getenv("BINANCE_FUTURES_API_KEY", os.getenv("BINANCE_API_KEY", "")).strip(),
            'secret': os.getenv("BINANCE_FUTURES_SECRET_KEY", os.getenv("BINANCE_SECRET_KEY", "")).strip(),
            'enableRateLimit': True,
            'options': {'adjustForTimeDifference': True, 'recvWindow': 15000, 'defaultType': 'future'}
        })
        self.ex.set_sandbox_mode(True)
        self.trades = deque(maxlen=100)
        self.positions: dict[str, dict] = {}  # تتبع المراكز المفتوحة

    def fix_pair(self, pair: str) -> str:
        pair = pair.upper().strip().replace("USDTUSDT","USDT").replace(".P","")
        if "/" in pair: return pair
        if pair.endswith("USDT"): return f"{pair[:-4]}/USDT"
        return f"{pair}/USDT"

    async def get_balance(self):
        try:
            bal = self.ex.fetch_balance({'type': 'future'})
            usdt = float(bal['total'].get('USDT', 0.0))
            # جلب المراكز المفتوحة
            positions_data = {}
            try:
                positions = self.ex.fetch_positions()
                for p in positions:
                    if p and float(p.get('contracts', 0) or 0) > 0:
                        sym = p['symbol']
                        positions_data[sym] = {
                            'side': p['side'],
                            'size': p['contracts'],
                            'entry_price': p['entryPrice'],
                            'unrealized_pnl': round(float(p.get('unrealizedPnl', 0) or 0), 2),
                            'leverage': p.get('leverage', settings['leverage'])
                        }
            except: pass

            pnl = usdt - INITIAL_BALANCE_FUTURES
            return {
                'usdt': round(usdt, 2),
                'total': round(usdt, 2),
                'pnl': round(pnl, 2),
                'pnl_pct': round((pnl / INITIAL_BALANCE_FUTURES) * 100, 2),
                'holdings': positions_data
            }
        except Exception as e:
            print(f"⚠️ Futures balance error: {e}")
            return {'usdt': 0.0, 'total': INITIAL_BALANCE_FUTURES, 'pnl': 0.0, 'pnl_pct': 0.0, 'holdings': {}}

    def execute(self, pair: str, direction: str, reason: str = "") -> dict:
        direction = direction.lower().strip()
        pair = self.fix_pair(pair)
        print(f"📡 [FUTURES] {direction} | {pair} | reason: {reason}")
        try:
            self.ex.load_markets()
            price = float(self.ex.fetch_ticker(pair)['last'])

            # ضبط الرافعة المالية
            try:
                self.ex.set_leverage(settings['leverage'], pair)
            except: pass

            trade_pnl = 0.0
            val = settings["futures_value"]

            if direction == "long_open":
                amt = float(self.ex.amount_to_precision(pair, val / price))
                self.ex.create_market_buy_order(pair, amt, {'reduceOnly': False})
                self.positions[pair] = {'side': 'long', 'entry': price, 'amt': amt}
                msg = f"✅ Long {amt} × {settings['leverage']}x"
                action_type = "long_open"

            elif direction == "long_close":
                pos = self.positions.get(pair, {})
                amt = pos.get('amt', float(self.ex.amount_to_precision(pair, val / price)))
                self.ex.create_market_sell_order(pair, amt, {'reduceOnly': True})
                if pair in self.positions:
                    entry = self.positions[pair].get('entry', price)
                    trade_pnl = round((price - entry) * amt * settings['leverage'], 2)
                    del self.positions[pair]
                pnl_str = f"+{trade_pnl}$" if trade_pnl >= 0 else f"{trade_pnl}$"
                reason_ar = {"stop_loss": "وقف خسارة", "peak_exit": "ذروة", "trailing_stop": "وقف متحرك"}.get(reason, "إغلاق")
                msg = f"✅ إغلاق Long [{reason_ar}] PnL: {pnl_str}"
                action_type = "long_close"

            elif direction == "short_open":
                amt = float(self.ex.amount_to_precision(pair, val / price))
                self.ex.create_market_sell_order(pair, amt, {'reduceOnly': False})
                self.positions[pair] = {'side': 'short', 'entry': price, 'amt': amt}
                msg = f"✅ Short {amt} × {settings['leverage']}x"
                action_type = "short_open"

            elif direction == "short_close":
                pos = self.positions.get(pair, {})
                amt = pos.get('amt', float(self.ex.amount_to_precision(pair, val / price)))
                self.ex.create_market_buy_order(pair, amt, {'reduceOnly': True})
                if pair in self.positions:
                    entry = self.positions[pair].get('entry', price)
                    trade_pnl = round((entry - price) * amt * settings['leverage'], 2)
                    del self.positions[pair]
                pnl_str = f"+{trade_pnl}$" if trade_pnl >= 0 else f"{trade_pnl}$"
                reason_ar = {"stop_loss": "وقف خسارة", "peak_exit": "ذروة", "trailing_stop": "وقف متحرك"}.get(reason, "إغلاق")
                msg = f"✅ إغلاق Short [{reason_ar}] PnL: {pnl_str}"
                action_type = "short_close"

            # دعم buy/sell العادي كـ alias
            elif direction == "buy":
                return self.execute(pair, "long_open", reason)
            elif direction == "sell":
                # إذا في مركز long أغلقه، وإلا افتح short
                if pair in self.positions and self.positions[pair]['side'] == 'long':
                    return self.execute(pair, "long_close", reason)
                else:
                    return self.execute(pair, "short_open", reason)
            else:
                raise Exception(f"أمر غير معروف: {direction}")

            res = {
                'id': int(datetime.now().timestamp() * 1000),
                'time': datetime.now().strftime("%H:%M:%S"),
                'date': datetime.now().strftime("%d/%m"),
                'market': 'FUTURES',
                'pair': pair, 'act': action_type,
                'price': price, 'pnl': trade_pnl,
                'reason': reason, 'st': msg, 'success': True
            }
            self.trades.appendleft(res)
            print(f"💰 [FUTURES] {msg}")
            return res

        except Exception as e:
            err = str(e)
            print(f"❌ [FUTURES] {err}")
            res = {
                'id': int(datetime.now().timestamp() * 1000),
                'time': datetime.now().strftime("%H:%M:%S"),
                'date': datetime.now().strftime("%d/%m"),
                'market': 'FUTURES', 'pair': pair, 'act': direction,
                'price': 0, 'pnl': 0, 'reason': reason,
                'st': f"❌ {err[:80]}", 'success': False
            }
            self.trades.appendleft(res)
            return res

    def close_all(self):
        for pair, pos in list(self.positions.items()):
            try:
                if pos['side'] == 'long':
                    self.ex.create_market_sell_order(pair, pos['amt'], {'reduceOnly': True})
                else:
                    self.ex.create_market_buy_order(pair, pos['amt'], {'reduceOnly': True})
                del self.positions[pair]
                print(f"🔴 [FUTURES] إغلاق {pos['side']} {pair}")
            except Exception as e:
                print(f"⚠️ فشل إغلاق {pair}: {e}")


spot_bot    = SpotBot()
futures_bot = FuturesBot()


async def broadcast(data: dict):
    disconnected = []
    for ws in active_connections:
        try: await ws.send_json(data)
        except: disconnected.append(ws)
    for ws in disconnected:
        if ws in active_connections: active_connections.remove(ws)


async def get_full_state():
    spot_bal    = await spot_bot.get_balance()
    futures_bal = await futures_bot.get_balance()
    all_trades  = sorted(
        list(spot_bot.trades) + list(futures_bot.trades),
        key=lambda x: x.get('id', 0), reverse=True
    )[:100]
    return {
        "spot":    spot_bal,
        "futures": futures_bal,
        "trades":  all_trades,
        "settings": settings
    }


HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SOVEREIGN V6</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&family=Tajawal:wght@300;400;700;900&display=swap" rel="stylesheet">
<style>
:root{--bg:#060810;--surface:#0d1117;--border:rgba(255,255,255,0.06);--gold:#f0b429;--gold-dim:rgba(240,180,41,0.12);--green:#00e676;--green-dim:rgba(0,230,118,0.1);--red:#ff4757;--red-dim:rgba(255,71,87,0.1);--blue:#00b4d8;--blue-dim:rgba(0,180,216,0.1);--purple:#a855f7;--purple-dim:rgba(168,85,247,0.1);--text:#e2e8f0;--muted:#4a5568;--mono:'IBM Plex Mono',monospace;--ar:'Tajawal',sans-serif}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:var(--ar);min-height:100vh}
body::before{content:'';position:fixed;inset:0;background-image:linear-gradient(rgba(240,180,41,0.02) 1px,transparent 1px),linear-gradient(90deg,rgba(240,180,41,0.02) 1px,transparent 1px);background-size:48px 48px;pointer-events:none;z-index:0}
.wrap{max-width:1300px;margin:0 auto;padding:20px;position:relative;z-index:1}

/* Header */
.header{display:flex;align-items:center;justify-content:space-between;padding:18px 28px;background:var(--surface);border:1px solid var(--border);border-radius:16px;margin-bottom:14px;position:relative;overflow:hidden}
.header::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,transparent,var(--gold),transparent)}
.logo{font-family:var(--mono);font-size:20px;font-weight:700;color:var(--gold);letter-spacing:3px;text-shadow:0 0 20px rgba(240,180,41,.3)}
.logo-sub{color:var(--muted);font-size:10px;letter-spacing:2px;display:block;margin-top:2px}
.status{display:flex;align-items:center;gap:8px;padding:7px 14px;border-radius:20px;font-size:11px;font-family:var(--mono);font-weight:600;border:1px solid;transition:all .3s}
.status.on{color:var(--green);border-color:rgba(0,230,118,.3);background:var(--green-dim)}
.status.off{color:var(--red);border-color:rgba(255,71,87,.3);background:var(--red-dim)}
.dot{width:7px;height:7px;border-radius:50%;background:currentColor;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

/* Ticker */
.ticker{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:9px 18px;margin-bottom:14px;font-family:var(--mono);font-size:11px;color:var(--muted);display:flex;align-items:center;gap:12px}
.ticker-live{color:var(--gold);font-weight:700;background:var(--gold-dim);padding:3px 10px;border-radius:4px}

/* Control Panel */
.ctrl{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px 22px;margin-bottom:14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ctrl-label{font-size:10px;font-family:var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:1.5px}
.btn{padding:8px 16px;border-radius:8px;font-family:var(--mono);font-size:11px;font-weight:700;cursor:pointer;border:1px solid;transition:all .2s;letter-spacing:1px;display:inline-flex;align-items:center;gap:5px}
.btn-green{background:var(--green-dim);color:var(--green);border-color:rgba(0,230,118,.3)}
.btn-green:hover{background:rgba(0,230,118,.2)}
.btn-yellow{background:rgba(255,200,0,.1);color:#ffc800;border-color:rgba(255,200,0,.3)}
.btn-yellow:hover{background:rgba(255,200,0,.18)}
.btn-red{background:var(--red-dim);color:var(--red);border-color:rgba(255,71,87,.3)}
.btn-red:hover{background:rgba(255,71,87,.25)}
.btn-blue{background:var(--blue-dim);color:var(--blue);border-color:rgba(0,180,216,.3)}
.btn-blue:hover{background:rgba(0,180,216,.2)}
.btn-gray{background:rgba(255,255,255,.04);color:var(--muted);border-color:var(--border)}
.state-badge{padding:6px 12px;border-radius:20px;font-family:var(--mono);font-size:11px;font-weight:700;border:1px solid}
.state-on{background:var(--green-dim);color:var(--green);border-color:rgba(0,230,118,.3)}
.state-off{background:rgba(255,200,0,.1);color:#ffc800;border-color:rgba(255,200,0,.3)}
.state-emergency{background:var(--red-dim);color:var(--red);border-color:rgba(255,71,87,.4);animation:ep 1s infinite}
@keyframes ep{0%,100%{opacity:1}50%{opacity:.4}}
.divider{width:1px;height:26px;background:var(--border)}
.lev-control{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:11px}
.lev-control label{color:var(--muted)}
.lev-input{background:rgba(255,255,255,.05);border:1px solid var(--border);color:var(--gold);font-family:var(--mono);font-size:12px;font-weight:700;width:52px;padding:5px 8px;border-radius:6px;text-align:center}
.lev-input:focus{outline:none;border-color:rgba(240,180,41,.4)}

/* Dual Balance Grid */
.balance-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}
@media(max-width:700px){.balance-grid{grid-template-columns:1fr}}
.balance-panel{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:18px;position:relative;overflow:hidden}
.balance-panel.spot-panel{border-color:rgba(0,180,216,.15)}
.balance-panel.futures-panel{border-color:rgba(168,85,247,.15)}
.balance-panel::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
.spot-panel::before{background:linear-gradient(90deg,transparent,var(--blue),transparent)}
.futures-panel::before{background:linear-gradient(90deg,transparent,var(--purple),transparent)}
.panel-title{font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:2px;text-transform:uppercase;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.spot-panel .panel-title{color:var(--blue)}
.futures-panel .panel-title{color:var(--purple)}
.panel-tag{padding:2px 8px;border-radius:4px;font-size:9px}
.spot-tag{background:var(--blue-dim);color:var(--blue);border:1px solid rgba(0,180,216,.2)}
.futures-tag{background:var(--purple-dim);color:var(--purple);border:1px solid rgba(168,85,247,.2)}
.bal-row{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.bal-item .label{font-size:9px;color:var(--muted);font-family:var(--mono);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
.bal-item .value{font-family:var(--mono);font-size:16px;font-weight:700}
.bal-item .sub{font-size:9px;color:var(--muted);font-family:var(--mono);margin-top:2px}
.c-gold{color:var(--gold)} .c-blue{color:var(--blue)} .c-green{color:var(--green)} .c-red{color:var(--red)} .c-purple{color:var(--purple)} .c-muted{color:var(--muted)}

/* Holdings chips */
.holdings{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.chip{background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:8px;padding:6px 12px;font-family:var(--mono);font-size:10px;display:flex;align-items:center;gap:6px}
.chip-coin{font-weight:700}
.pos{color:var(--green)} .neg{color:var(--red)}

/* Trades Table */
.section{background:var(--surface);border:1px solid var(--border);border-radius:16px;overflow:hidden}
.section-head{padding:14px 22px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.section-title{font-size:11px;font-family:var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:2px}
.count-badge{font-family:var(--mono);font-size:10px;color:var(--gold);background:var(--gold-dim);padding:3px 10px;border-radius:20px}
table{width:100%;border-collapse:collapse}
thead th{padding:10px 18px;font-size:9px;font-family:var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:1.5px;text-align:right;background:rgba(255,255,255,.02);border-bottom:1px solid var(--border)}
tbody tr{border-bottom:1px solid rgba(255,255,255,.03);transition:background .2s}
tbody tr:hover{background:rgba(255,255,255,.02)}
tbody tr.flash{animation:flash 1.5s ease-out}
@keyframes flash{0%{background:rgba(240,180,41,.15)}100%{background:transparent}}
td{padding:12px 18px;font-size:12px;text-align:right;vertical-align:middle}
.t-time{font-family:var(--mono);color:var(--muted);font-size:10px}
.t-pair{font-family:var(--mono);font-weight:700}
.t-price{font-family:var(--mono);color:var(--gold)}
.badge{display:inline-block;padding:3px 10px;border-radius:5px;font-family:var(--mono);font-size:10px;font-weight:700;letter-spacing:1px}
.b-buy{background:var(--green-dim);color:var(--green);border:1px solid rgba(0,230,118,.2)}
.b-sell{background:var(--red-dim);color:var(--red);border:1px solid rgba(255,71,87,.2)}
.b-long{background:var(--blue-dim);color:var(--blue);border:1px solid rgba(0,180,216,.2)}
.b-short{background:var(--purple-dim);color:var(--purple);border:1px solid rgba(168,85,247,.2)}
.b-lclose{background:rgba(0,180,216,.06);color:var(--blue);border:1px solid rgba(0,180,216,.15)}
.b-sclose{background:rgba(168,85,247,.06);color:var(--purple);border:1px solid rgba(168,85,247,.15)}
.market-tag{font-family:var(--mono);font-size:9px;padding:2px 6px;border-radius:3px;font-weight:700}
.mt-spot{background:var(--blue-dim);color:var(--blue)}
.mt-futures{background:var(--purple-dim);color:var(--purple)}
.pnl{font-family:var(--mono);font-weight:700;font-size:12px}
.t-status{font-size:10px;color:var(--muted);max-width:200px}
.empty{padding:50px;text-align:center;color:var(--muted);font-family:var(--mono);font-size:12px}
.empty span{font-size:36px;display:block;margin-bottom:12px;opacity:.2}

/* Modal */
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.85);z-index:100;align-items:center;justify-content:center}
.modal-box{background:#0d1117;border:1px solid rgba(240,180,41,.2);border-radius:18px;padding:28px;max-width:540px;width:90%;max-height:80vh;overflow-y:auto}
.modal-title{font-family:var(--mono);color:var(--gold);font-weight:700;letter-spacing:2px;font-size:13px}

::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
</style>
</head>
<body>
<div class="wrap">

  <!-- Header -->
  <div class="header">
    <div class="logo">SOVEREIGN<span class="logo-sub">SPOT + FUTURES · V6.0 · TESTNET</span></div>
    <div id="sb" class="status off"><div class="dot"></div><span id="st">جاري الاتصال...</span></div>
  </div>

  <!-- Ticker -->
  <div class="ticker">
    <span class="ticker-live">⚡ LIVE</span>
    <span id="clock">--:--:--</span>
    <span style="flex:1"></span>
    <span>آخر تحديث:</span><span id="upd" style="color:var(--text);margin-right:4px">--</span>
  </div>

  <!-- Control Panel -->
  <div class="ctrl">
    <span class="ctrl-label">التحكم</span>
    <span id="botStateBadge" class="state-badge state-on">⏳ تحميل</span>
    <div class="divider"></div>
    <button class="btn btn-yellow" id="toggleBtn" onclick="toggleBot()">⏸ إيقاف</button>
    <button class="btn btn-blue" onclick="showPortfolio()">📊 المحفظة</button>
    <div class="divider"></div>
    <div class="lev-control">
      <label>Leverage:</label>
      <input class="lev-input" id="levInput" type="number" min="1" max="125" value="10" onchange="setLeverage(this.value)">
      <span style="color:var(--purple);font-family:var(--mono);font-size:11px">×</span>
    </div>
    <div class="divider"></div>
    <button class="btn btn-red" onclick="liq()">⚠ تصفية Spot</button>
    <button class="btn btn-red" onclick="liqFutures()">⚠ إغلاق Futures</button>
    <button class="btn btn-red" id="emergencyBtn" onclick="emergencyStop()">🚨 طوارئ</button>
    <button class="btn btn-green" id="resumeBtn" style="display:none" onclick="resume()">▶ استئناف</button>
  </div>

  <!-- Dual Balance -->
  <div class="balance-grid">
    <!-- Spot -->
    <div class="balance-panel spot-panel">
      <div class="panel-title">💧 SPOT <span class="panel-tag spot-tag">Testnet</span></div>
      <div class="bal-row">
        <div class="bal-item"><div class="label">المحفظة</div><div class="value c-gold" id="sTot">--</div><div class="sub">USDT</div></div>
        <div class="bal-item"><div class="label">USDT الحر</div><div class="value c-blue" id="sUsd">--</div><div class="sub">متاح</div></div>
        <div class="bal-item"><div class="label">PnL</div><div class="value" id="sPnl">--</div><div class="sub" id="sPnlPct">--</div></div>
      </div>
      <div class="holdings" id="sHoldings"></div>
    </div>
    <!-- Futures -->
    <div class="balance-panel futures-panel">
      <div class="panel-title">⚡ FUTURES <span class="panel-tag futures-tag">Testnet</span></div>
      <div class="bal-row">
        <div class="bal-item"><div class="label">الرصيد</div><div class="value c-gold" id="fTot">--</div><div class="sub">USDT</div></div>
        <div class="bal-item"><div class="label">مراكز مفتوحة</div><div class="value c-purple" id="fPos">0</div><div class="sub">مركز</div></div>
        <div class="bal-item"><div class="label">PnL</div><div class="value" id="fPnl">--</div><div class="sub" id="fPnlPct">--</div></div>
      </div>
      <div class="holdings" id="fHoldings"></div>
    </div>
  </div>

  <!-- Trades Table -->
  <div class="section">
    <div class="section-head">
      <span class="section-title">سجل الصفقات — Spot + Futures</span>
      <span class="count-badge" id="countBadge">0 صفقة</span>
    </div>
    <div style="overflow-x:auto">
      <table>
        <thead><tr>
          <th>التاريخ</th><th>الوقت</th><th>السوق</th><th>الزوج</th>
          <th>النوع</th><th>السعر</th><th>PnL</th><th>الحالة</th>
        </tr></thead>
        <tbody id="tb">
          <tr><td colspan="8"><div class="empty"><span>📡</span>في انتظار الإشارات...</div></td></tr>
        </tbody>
      </table>
    </div>
  </div>
</div>

<!-- Portfolio Modal -->
<div id="pModal" class="modal">
  <div class="modal-box">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <span class="modal-title">📊 تفاصيل المحفظة</span>
      <button onclick="document.getElementById('pModal').style.display='none'" style="background:none;border:none;color:var(--muted);cursor:pointer;font-size:18px">✕</button>
    </div>
    <div id="pContent">جاري التحميل...</div>
  </div>
</div>

<script>
let delay=2000, known=new Set();

function connect(){
  const ws=new WebSocket((location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws');
  ws.onopen=()=>{document.getElementById('sb').className='status on';document.getElementById('st').textContent='متصل · LIVE';delay=2000;};
  ws.onmessage=e=>render(JSON.parse(e.data));
  ws.onclose=()=>{document.getElementById('sb').className='status off';document.getElementById('st').textContent='انقطع...';setTimeout(connect,delay);delay=Math.min(delay*1.5,30000);};
  ws.onerror=()=>ws.close();
}

function fmt(n,d=2){return Number(n).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});}

function pnlHtmlCard(pnl,pct){
  const cls=pnl>0?'c-green':pnl<0?'c-red':'c-muted';
  const sign=pnl>=0?'+':'';
  return `<div class="value ${cls}" id="">${sign}${fmt(pnl)}</div><div class="sub">${sign}${pct}%</div>`;
}

function render(d){
  const now=new Date();
  document.getElementById('clock').textContent=now.toLocaleTimeString('ar-SA');
  document.getElementById('upd').textContent=now.toLocaleTimeString('ar-SA');

  if(d.settings) updateControls(d.settings);

  // Spot balance
  const s=d.spot;
  document.getElementById('sTot').textContent=fmt(s.total);
  document.getElementById('sUsd').textContent=fmt(s.usdt);
  const spnl=document.getElementById('sPnl');
  spnl.textContent=(s.pnl>=0?'+':'')+fmt(s.pnl);
  spnl.className='value '+(s.pnl>0?'c-green':s.pnl<0?'c-red':'c-muted');
  document.getElementById('sPnlPct').textContent=(s.pnl>=0?'+':'')+s.pnl_pct+'%';
  document.getElementById('sHoldings').innerHTML=Object.entries(s.holdings||{}).map(([c,v])=>`
    <div class="chip"><span class="chip-coin c-blue">${c}</span><span>${v.amount}</span><span class="c-muted">@</span><span>${fmt(v.price,2)}</span><span class="${v.unrealized_pnl>=0?'pos':'neg'}">${v.unrealized_pnl>=0?'+':''}${fmt(v.unrealized_pnl,2)}$</span></div>`).join('');

  // Futures balance
  const f=d.futures;
  document.getElementById('fTot').textContent=fmt(f.total);
  document.getElementById('fPos').textContent=Object.keys(f.holdings||{}).length;
  const fpnl=document.getElementById('fPnl');
  fpnl.textContent=(f.pnl>=0?'+':'')+fmt(f.pnl);
  fpnl.className='value '+(f.pnl>0?'c-green':f.pnl<0?'c-red':'c-muted');
  document.getElementById('fPnlPct').textContent=(f.pnl>=0?'+':'')+f.pnl_pct+'%';
  document.getElementById('fHoldings').innerHTML=Object.entries(f.holdings||{}).map(([sym,p])=>`
    <div class="chip"><span class="chip-coin c-purple">${sym}</span><span class="${p.side==='long'?'pos':'neg'}">${p.side.toUpperCase()}</span><span>${p.leverage}x</span><span class="${p.unrealized_pnl>=0?'pos':'neg'}">${p.unrealized_pnl>=0?'+':''}${fmt(p.unrealized_pnl,2)}$</span></div>`).join('');

  // Trades
  const trades=d.trades||[];
  document.getElementById('countBadge').textContent=trades.length+' صفقة';
  if(!trades.length){
    document.getElementById('tb').innerHTML='<tr><td colspan="8"><div class="empty"><span>📡</span>في انتظار الإشارات...</div></td></tr>';
    return;
  }
  document.getElementById('tb').innerHTML=trades.map(x=>{
    const isNew=!known.has(x.id); if(isNew)known.add(x.id);
    const badgeMap={
      'buy':'<span class="badge b-buy">شراء</span>',
      'sell':'<span class="badge b-sell">بيع</span>',
      'long_open':'<span class="badge b-long">LONG ▲</span>',
      'long_close':'<span class="badge b-lclose">إغلاق Long</span>',
      'short_open':'<span class="badge b-short">SHORT ▼</span>',
      'short_close':'<span class="badge b-sclose">إغلاق Short</span>',
    };
    const badge=badgeMap[x.act]||`<span class="badge b-sell">${x.act}</span>`;
    const mkt=x.market==='FUTURES'?'<span class="market-tag mt-futures">F</span>':'<span class="market-tag mt-spot">S</span>';
    const hasPnl=x.pnl!==0;
    const pnlHtml=hasPnl?`<span class="pnl ${x.pnl>0?'pos':'neg'}">${x.pnl>0?'+':''}${fmt(x.pnl,2)}$</span>`:'<span class="c-muted" style="font-family:var(--mono)">—</span>';
    return `<tr class="${isNew?'flash':''}">
      <td class="t-time">${x.date||'--'}</td>
      <td class="t-time">${x.time}</td>
      <td>${mkt}</td>
      <td class="t-pair">${x.pair}</td>
      <td>${badge}</td>
      <td class="t-price">${x.price>0?fmt(x.price,4):'—'}</td>
      <td>${pnlHtml}</td>
      <td class="t-status">${x.st}</td>
    </tr>`;
  }).join('');
}

function updateControls(s){
  const badge=document.getElementById('botStateBadge');
  const toggleBtn=document.getElementById('toggleBtn');
  const emergencyBtn=document.getElementById('emergencyBtn');
  const resumeBtn=document.getElementById('resumeBtn');
  document.getElementById('levInput').value=s.leverage||10;
  if(s.emergency_stop){
    badge.textContent='🚨 طوارئ';badge.className='state-badge state-emergency';
    toggleBtn.style.display='none';emergencyBtn.style.display='none';resumeBtn.style.display='inline-flex';
  } else if(s.active){
    badge.textContent='✅ نشط';badge.className='state-badge state-on';
    toggleBtn.textContent='⏸ إيقاف';toggleBtn.className='btn btn-yellow';
    toggleBtn.style.display='inline-flex';emergencyBtn.style.display='inline-flex';resumeBtn.style.display='none';
  } else {
    badge.textContent='⏸ متوقف';badge.className='state-badge state-off';
    toggleBtn.textContent='▶ تشغيل';toggleBtn.className='btn btn-green';
    toggleBtn.style.display='inline-flex';emergencyBtn.style.display='inline-flex';resumeBtn.style.display='none';
  }
}

async function toggleBot(){await fetch('/control/toggle',{method:'POST'});}
async function emergencyStop(){
  if(!confirm('🚨 إيقاف طوارئ: سيوقف البوت ويغلق جميع المراكز!\nمتأكد؟'))return;
  await fetch('/control/emergency',{method:'POST'});
}
async function resume(){await fetch('/control/resume',{method:'POST'});}
async function liq(){
  if(!confirm('تصفية جميع مراكز Spot؟'))return;
  await fetch('/liquidate',{method:'POST'});
}
async function liqFutures(){
  if(!confirm('إغلاق جميع مراكز Futures؟'))return;
  await fetch('/liquidate/futures',{method:'POST'});
}
async function setLeverage(val){
  await fetch('/control/leverage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({leverage:parseInt(val)})});
}

async function showPortfolio(){
  document.getElementById('pModal').style.display='flex';
  document.getElementById('pContent').innerHTML='<div style="text-align:center;padding:20px;color:var(--muted);font-family:var(--mono)">⏳ تحميل...</div>';
  try{
    const res=await fetch('/portfolio');const d=await res.json();
    const s=d.spot,f=d.futures;
    document.getElementById('pContent').innerHTML=`
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px">
        <div style="background:var(--blue-dim);border:1px solid rgba(0,180,216,.2);border-radius:10px;padding:14px">
          <div style="color:var(--blue);font-family:var(--mono);font-size:10px;letter-spacing:1px;margin-bottom:8px">SPOT</div>
          <div style="color:var(--gold);font-family:var(--mono);font-size:17px;font-weight:700">${fmt(s.total)} USDT</div>
          <div style="color:${s.pnl>=0?'var(--green)':'var(--red)'};font-family:var(--mono);font-size:12px;margin-top:4px">${s.pnl>=0?'+':''}${fmt(s.pnl)}$ (${s.pnl_pct}%)</div>
        </div>
        <div style="background:var(--purple-dim);border:1px solid rgba(168,85,247,.2);border-radius:10px;padding:14px">
          <div style="color:var(--purple);font-family:var(--mono);font-size:10px;letter-spacing:1px;margin-bottom:8px">FUTURES × ${d.settings.leverage}</div>
          <div style="color:var(--gold);font-family:var(--mono);font-size:17px;font-weight:700">${fmt(f.total)} USDT</div>
          <div style="color:${f.pnl>=0?'var(--green)':'var(--red)'};font-family:var(--mono);font-size:12px;margin-top:4px">${f.pnl>=0?'+':''}${fmt(f.pnl)}$ (${f.pnl_pct}%)</div>
        </div>
      </div>
      <div style="color:var(--muted);font-family:var(--mono);font-size:9px;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:8px">إعدادات البوت</div>
      <div style="background:rgba(255,255,255,.03);border-radius:10px;padding:14px;font-family:var(--mono);font-size:11px;display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <div><span style="color:var(--muted)">Spot Buy: </span><span style="color:var(--gold)">${d.settings.spot_buy_value}$ (${d.settings.spot_buy_mode})</span></div>
        <div><span style="color:var(--muted)">Futures: </span><span style="color:var(--purple)">${d.settings.futures_value}$ × ${d.settings.leverage}x</span></div>
        <div><span style="color:var(--muted)">الحالة: </span><span style="color:${d.settings.active?'var(--green)':'var(--red)'}">${d.settings.active?'نشط':'متوقف'}</span></div>
        <div><span style="color:var(--muted)">Futures: </span><span style="color:${d.settings.futures_enabled?'var(--green)':'var(--red)'}">${d.settings.futures_enabled?'مفعل':'معطل'}</span></div>
      </div>`;
  }catch(e){document.getElementById('pContent').innerHTML='<div style="color:var(--red)">❌ خطأ</div>';}
}

connect();
setInterval(()=>{const el=document.getElementById('clock');if(el)el.textContent=new Date().toLocaleTimeString('ar-SA');},1000);
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def root(): return HTML


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    active_connections.append(ws)
    print(f"🔌 اتصال جديد | {len(active_connections)}")
    try:
        await ws.send_json(await get_full_state())
        while True:
            await asyncio.sleep(5)
            await ws.send_json(await get_full_state())
    except: pass
    finally:
        if ws in active_connections: active_connections.remove(ws)
        print(f"🔌 انقطع | {len(active_connections)}")


@app.post("/webhook")
async def webhook(s: Signal):
    if settings.get("emergency_stop"): return {"status": "emergency_stop"}
    if not settings.get("active"):     return {"status": "inactive"}

    direction = s.direction.lower()
    reason    = s.reason or ""
    market    = (s.market or "spot").lower()

    # تحديد السوق تلقائياً حسب نوع الأمر
    if direction in ["long_open", "long_close", "short_open", "short_close"]:
        market = "futures"

    if market == "futures":
        if not settings.get("futures_enabled"):
            return {"status": "futures_disabled"}
        result = futures_bot.execute(s.pair, direction, reason)
    else:
        result = spot_bot.execute(s.pair, direction, reason)

    await broadcast(await get_full_state())
    return result


@app.post("/liquidate")
async def liquidate():
    spot_bot.liquidate_all()
    await broadcast(await get_full_state())
    return {"ok": True}


@app.post("/liquidate/futures")
async def liquidate_futures():
    futures_bot.close_all()
    await broadcast(await get_full_state())
    return {"ok": True}


@app.post("/control/toggle")
async def toggle():
    settings["active"] = not settings["active"]
    await broadcast(await get_full_state())
    return {"active": settings["active"]}


@app.post("/control/emergency")
async def emergency():
    settings["emergency_stop"] = True
    settings["active"] = False
    spot_bot.liquidate_all()
    futures_bot.close_all()
    await broadcast(await get_full_state())
    return {"ok": True}


@app.post("/control/resume")
async def resume():
    settings["emergency_stop"] = False
    settings["active"] = True
    await broadcast(await get_full_state())
    return {"ok": True}


@app.post("/control/leverage")
async def set_leverage(data: dict):
    lev = int(data.get("leverage", 10))
    lev = max(1, min(125, lev))
    settings["leverage"] = lev
    print(f"🎚️ Leverage → {lev}x")
    await broadcast(await get_full_state())
    return {"leverage": lev}


@app.get("/portfolio")
async def portfolio():
    s = await get_full_state()
    s["spot_trades"]    = list(spot_bot.trades)[:10]
    s["futures_trades"] = list(futures_bot.trades)[:10]
    return s


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "spot_trades":    len(spot_bot.trades),
        "futures_trades": len(futures_bot.trades),
        "connections":    len(active_connections),
        "leverage":       settings["leverage"]
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
