"""
╔══════════════════════════════════════════════════════════════╗
║           SOVEREIGN TRADING SYSTEM — V7.0                   ║
║           Spot + Futures | Risk Management | Full Dashboard  ║
║           Built with FastAPI + CCXT + WebSocket             ║
╚══════════════════════════════════════════════════════════════╝

متغيرات البيئة المطلوبة في Render:
  BINANCE_API_KEY              ← مفتاح Spot
  BINANCE_SECRET_KEY           ← سر Spot
  BINANCE_FUTURES_API_KEY      ← مفتاح Futures (اختياري)
  BINANCE_FUTURES_SECRET_KEY   ← سر Futures (اختياري)
  DASHBOARD_PASSWORD           ← كلمة سر الداشبورد (افتراضي: sovereign2025)
  INITIAL_BALANCE              ← رأس المال الابتدائي (افتراضي: 10000)
  TELEGRAM_TOKEN               ← توكن بوت Telegram (اختياري)
  TELEGRAM_CHAT_ID             ← معرف المحادثة (اختياري)
"""

import os, asyncio, ccxt, uvicorn, json
from datetime import datetime, timedelta
from collections import deque
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import httpx

# ══════════════════════════════════════════
# تهيئة التطبيق
# ══════════════════════════════════════════
app = FastAPI(title="SOVEREIGN V7.0", version="7.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ══════════════════════════════════════════
# الإعدادات والثوابت
# ══════════════════════════════════════════
DASHBOARD_PASSWORD    = os.getenv("DASHBOARD_PASSWORD", "sovereign2025")
INITIAL_BALANCE       = float(os.getenv("INITIAL_BALANCE", "10000"))
TELEGRAM_TOKEN        = os.getenv("TELEGRAM_TOKEN", "8591906557:AAGxYzhXFOBGdqSpvIXJtiPuPj8oUSwdP8w")
TELEGRAM_CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID", "1770637")

# الإعدادات الافتراضية — كل ميزة قابلة للتفعيل/الإلغاء
settings = {
    # ─── حالة البوت ───────────────────────
    "active":           True,
    "emergency_stop":   False,

    # ─── Spot ─────────────────────────────
    "spot_buy_mode":    "fixed",    # fixed | percent
    "spot_buy_value":   100.0,
    "spot_sell_ratio":  1.0,

    # ─── Futures ──────────────────────────
    "futures_enabled":  True,
    "futures_mode":     "fixed",
    "futures_value":    100.0,
    "leverage":         10,

    # ─── Risk Management ──────────────────
    "risk_enabled":             True,
    "trailing_stop_pct":        1.2,
    "fixed_stop_loss_pct":      3.0,

    # ─── حد الخسارة اليومي ───────────────
    "daily_loss_enabled":       True,
    "daily_loss_limit_pct":     5.0,
    "daily_loss_current":       0.0,
    "daily_loss_date":          "",

    # ─── Session Manager ──────────────────
    "session_enabled":  False,
    "session_start":    "08:00",
    "session_end":      "22:00",

    # ─── التقويم الاقتصادي ────────────────
    "calendar_enabled":         False,
    "calendar_pause_before":    30,
    "calendar_resume_after":    60,
    "calendar_paused":          False,
    "calendar_next_event":      "",
    "calendar_next_event_time": "",

    # ─── Telegram ─────────────────────────
    "telegram_enabled":         bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
    "telegram_on_trade":        True,
    "telegram_on_error":        True,
    "telegram_daily_report":    True,
    "telegram_report_time":     "00:00",
}

active_connections: list[WebSocket] = []
error_logs: deque = deque(maxlen=100)


# ══════════════════════════════════════════
# Telegram
# ══════════════════════════════════════════
async def send_telegram(msg: str, force: bool = False):
    if not (force or settings.get("telegram_enabled")):
        return
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"}
            )
    except Exception as e:
        print(f"⚠️ Telegram: {e}")


def log_error(msg: str, notify: bool = True):
    entry = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "date": datetime.now().strftime("%d/%m"),
        "msg":  msg
    }
    error_logs.appendleft(entry)
    print(f"❌ {msg}")
    if notify and settings.get("telegram_on_error"):
        asyncio.create_task(send_telegram(f"⚠️ <b>تحذير</b>\n{msg[:200]}"))


# ══════════════════════════════════════════
# فحوصات الأمان
# ══════════════════════════════════════════
def is_session_active() -> tuple[bool, str]:
    if not settings.get("session_enabled"):
        return True, ""
    now = datetime.now().strftime("%H:%M")
    start, end = settings["session_start"], settings["session_end"]
    if start <= now <= end:
        return True, ""
    return False, f"خارج وقت الجلسة ({start} – {end})"


def is_calendar_paused() -> tuple[bool, str]:
    if not settings.get("calendar_enabled"):
        return False, ""
    if settings.get("calendar_paused"):
        ev = settings.get("calendar_next_event", "حدث اقتصادي")
        return True, ev
    return False, ""


def update_daily_loss(pnl: float) -> bool:
    """يحدّث الخسارة اليومية ويوقف البوت إذا تجاوز الحد. يُعيد True إذا وصل للحد."""
    if not settings.get("daily_loss_enabled"):
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    if settings["daily_loss_date"] != today:
        settings["daily_loss_current"] = 0.0
        settings["daily_loss_date"]    = today
    if pnl < 0:
        settings["daily_loss_current"] += pnl
        limit = INITIAL_BALANCE * (settings["daily_loss_limit_pct"] / 100) * -1
        if settings["daily_loss_current"] <= limit:
            settings["active"] = False
            asyncio.create_task(send_telegram(
                f"🚨 <b>إيقاف تلقائي</b>\n"
                f"تجاوز حد الخسارة اليومي!\n"
                f"الخسارة: {settings['daily_loss_current']:.2f}$\n"
                f"الحد المسموح: {abs(limit):.2f}$"
            ))
            return True
    return False


# ══════════════════════════════════════════
# جلب التقويم الاقتصادي
# ══════════════════════════════════════════
async def fetch_economic_calendar():
    if not settings.get("calendar_enabled"):
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
            events = resp.json()
        now = datetime.now()
        upcoming = []
        for ev in events:
            if ev.get("impact") not in ["High"]:
                continue
            try:
                dt_str = ev["date"].replace("Z", "+00:00")
                ev_time = datetime.fromisoformat(dt_str).replace(tzinfo=None)
                if ev_time > now:
                    upcoming.append({
                        "time":    ev_time,
                        "title":   ev.get("title", ""),
                        "country": ev.get("country", "")
                    })
            except:
                continue

        if not upcoming:
            settings["calendar_next_event"]      = ""
            settings["calendar_next_event_time"] = ""
            if settings.get("calendar_paused"):
                settings["calendar_paused"] = False
            return

        upcoming.sort(key=lambda x: x["time"])
        nxt = upcoming[0]
        settings["calendar_next_event"]      = f"🔴 {nxt['country']} — {nxt['title']}"
        settings["calendar_next_event_time"] = nxt["time"].strftime("%d/%m %H:%M")

        pause_start  = nxt["time"] - timedelta(minutes=settings["calendar_pause_before"])
        resume_after = nxt["time"] + timedelta(minutes=settings["calendar_resume_after"])

        if pause_start <= now <= resume_after:
            if not settings["calendar_paused"]:
                settings["calendar_paused"] = True
                await send_telegram(
                    f"⏸ <b>إيقاف مؤقت — حدث اقتصادي</b>\n"
                    f"{nxt['country']}: {nxt['title']}\n"
                    f"الوقت: {nxt['time'].strftime('%H:%M')}"
                )
        else:
            if settings["calendar_paused"]:
                settings["calendar_paused"] = False
                await send_telegram("▶️ <b>استئناف التداول</b>\nانتهى تأثير الحدث الاقتصادي ✅")

    except Exception as e:
        log_error(f"Calendar fetch: {e}", notify=False)


# ══════════════════════════════════════════
# SpotBot
# ══════════════════════════════════════════
class SpotBot:
    def __init__(self):
        self.ex = ccxt.binance({
            'apiKey':  os.getenv("BINANCE_API_KEY", "").strip(),
            'secret':  os.getenv("BINANCE_SECRET_KEY", "").strip(),
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
                'recvWindow': 15000,
                'defaultType': 'spot'
            }
        })
        self.ex.set_sandbox_mode(True)
        self.trades: deque      = deque(maxlen=500)
        self.buy_prices: dict   = {}
        self.buy_amounts: dict  = {}

    async def get_balance(self) -> dict:
        try:
            bal = self.ex.fetch_balance()
            usdt = float(bal['total'].get('USDT', 0.0))
            portfolio_value = usdt
            holdings = {}
            # جلب كل العملات الموجودة فعلياً — بدون قيود
            for coin, raw_amt in bal['total'].items():
                amt = float(raw_amt or 0)
                if coin in ('USDT','BUSD','USDC','TUSD','DAI') or amt < 0.000001:
                    continue
                try:
                    pair   = f"{coin}/USDT"
                    ticker = self.ex.fetch_ticker(pair)
                    price  = float(ticker['last'])
                    value  = amt * price
                    portfolio_value += value
                    buy_p   = self.buy_prices.get(coin, price)
                    pnl_usd = (price - buy_p) * amt
                    pnl_pct = ((price - buy_p) / buy_p * 100) if buy_p > 0 else 0.0
                    holdings[coin] = {
                        'amount':        round(amt, 6),
                        'buy_price':     round(buy_p, 6),
                        'current_price': round(price, 6),
                        'value':         round(value, 2),
                        'pnl_usd':       round(pnl_usd, 2),
                        'pnl_pct':       round(pnl_pct, 2),
                    }
                except Exception:
                    pass

            total_pnl = portfolio_value - INITIAL_BALANCE
            pnl_pct   = round((total_pnl / INITIAL_BALANCE) * 100, 2) if INITIAL_BALANCE else 0
            return {
                'usdt':     round(usdt, 2),
                'total':    round(portfolio_value, 2),
                'pnl':      round(total_pnl, 2),
                'pnl_pct':  pnl_pct,
                'holdings': holdings,
            }
        except Exception as e:
            log_error(f"Spot balance: {e}", notify=False)
            return {'usdt': 0.0, 'total': INITIAL_BALANCE, 'pnl': 0.0, 'pnl_pct': 0.0, 'holdings': {}}

    @staticmethod
    def fix_pair(pair: str) -> str:
        pair = pair.upper().strip().replace("USDTUSDT","USDT").replace(".P","")
        if "/" in pair:   return pair
        if pair.endswith("USDT"): return f"{pair[:-4]}/USDT"
        return f"{pair}/USDT"

    def _place_risk_orders(self, pair: str, amt: float, buy_price: float):
        if not settings.get("risk_enabled"):
            return
        # Fixed Stop Loss
        try:
            sl_price = round(buy_price * (1 - settings["fixed_stop_loss_pct"] / 100), 6)
            self.ex.create_order(pair, 'stop_loss_limit', 'sell', amt,
                                 sl_price, {'stopPrice': sl_price})
            print(f"🛡️ Fixed SL @ {sl_price}")
        except Exception as e:
            log_error(f"Fixed SL failed ({pair}): {e}", notify=False)
        # Trailing Stop
        try:
            self.ex.create_order(pair, 'trailing_stop_market', 'sell', amt, None, {
                'callbackRate': settings["trailing_stop_pct"]
            })
            print(f"🛡️ Trailing SL {settings['trailing_stop_pct']}%")
        except Exception as e:
            log_error(f"Trailing SL failed ({pair}): {e}", notify=False)

    def execute(self, pair: str, side: str, reason: str = "") -> dict:
        side = side.lower().strip()
        pair = self.fix_pair(pair)
        coin = pair.split('/')[0]
        price      = 0.0
        trade_pnl  = 0.0
        amt        = 0.0
        total_val  = 0.0
        action_type = side

        try:
            self.ex.load_markets()
            ticker = self.ex.fetch_ticker(pair)
            price  = float(ticker['last'])

            # ── شراء ──────────────────────────────
            if side in ("buy", "long_open"):
                bal  = self.ex.fetch_balance()
                usdt = float(bal['total'].get('USDT', 0.0))
                if settings["spot_buy_mode"] == "fixed":
                    val = settings["spot_buy_value"]
                else:
                    val = usdt * (settings["spot_buy_value"] / 100)
                val = max(val, 11.0)
                if val > usdt:
                    raise Exception(f"رصيد غير كافٍ ({usdt:.2f}$ < {val:.2f}$)")
                amt       = float(self.ex.amount_to_precision(pair, val / price))
                total_val = round(amt * price, 2)
                self.ex.create_market_buy_order(pair, amt)
                self.buy_prices[coin]  = price
                self.buy_amounts[coin] = amt
                self._place_risk_orders(pair, amt, price)
                action_type = "buy"
                msg = f"✅ شراء {amt} {coin} @ {price:,.4f} | {total_val}$"
                if settings.get("telegram_on_trade"):
                    asyncio.create_task(send_telegram(
                        f"🟢 <b>شراء — {coin}</b>\n"
                        f"الكمية: <code>{amt}</code>\n"
                        f"السعر: <code>{price:,.4f}</code>\n"
                        f"الإجمالي: <code>{total_val}$</code>"
                    ))

            # ── بيع ───────────────────────────────
            elif side in ("sell", "long_close"):
                bal   = self.ex.fetch_balance()
                c_bal = float(bal['total'].get(coin, 0.0))
                if c_bal < 0.000001:
                    raise Exception(f"لا يوجد رصيد من {coin}")
                sell_pct = settings["spot_sell_ratio"]
                amt      = float(self.ex.amount_to_precision(pair, c_bal * sell_pct))
                total_val = round(amt * price, 2)
                self.ex.create_market_sell_order(pair, amt)
                buy_p     = self.buy_prices.get(coin, price)
                trade_pnl = round((price - buy_p) * amt, 2)
                pnl_pct   = round(((price - buy_p) / buy_p * 100), 2) if buy_p > 0 else 0
                if coin in self.buy_prices:  del self.buy_prices[coin]
                if coin in self.buy_amounts: del self.buy_amounts[coin]
                update_daily_loss(trade_pnl)
                action_type = "sell"
                reason_ar   = _reason_ar(reason)
                sign        = "+" if trade_pnl >= 0 else ""
                msg = f"✅ بيع [{reason_ar}] {amt} {coin} @ {price:,.4f} | PnL: {sign}{trade_pnl}$ ({pnl_pct:+.2f}%)"
                if settings.get("telegram_on_trade"):
                    em = "🟢" if trade_pnl >= 0 else "🔴"
                    asyncio.create_task(send_telegram(
                        f"{em} <b>بيع — {coin}</b>\n"
                        f"السبب: {reason_ar}\n"
                        f"السعر: <code>{price:,.4f}</code>\n"
                        f"PnL: <code>{sign}{trade_pnl}$ ({pnl_pct:+.2f}%)</code>"
                    ))
            else:
                raise Exception(f"أمر غير معروف: {side}")

            record = _make_record(pair, action_type, "SPOT", price, amt, total_val, trade_pnl, reason, msg, True)
            self.trades.appendleft(record)
            print(f"💰 [SPOT] {msg}")
            return record

        except Exception as e:
            err = str(e)
            log_error(f"[SPOT] {side} {pair}: {err}")
            record = _make_record(pair, side, "SPOT", price, amt, total_val, 0, reason, f"❌ {err[:100]}", False)
            self.trades.appendleft(record)
            return record

    def liquidate_all(self):
        try:
            bal = self.ex.fetch_balance()
            for coin, raw in bal['total'].items():
                amt = float(raw or 0)
                if coin in ('USDT','BUSD','USDC','TUSD','DAI') or amt < 0.000001:
                    continue
                pair = f"{coin}/USDT"
                try:
                    self.ex.load_markets()
                    if pair in self.ex.markets:
                        self.ex.create_market_sell_order(pair, amt)
                        print(f"🔴 تصفية {coin}")
                except Exception as e:
                    log_error(f"Liquidate {coin}: {e}", notify=False)
        except Exception as e:
            log_error(f"Liquidate all: {e}", notify=False)

    def performance_stats(self) -> dict:
        trades = [t for t in self.trades if t.get('act') in ('sell','long_close') and t.get('success')]
        if not trades:
            return {'total':0,'wins':0,'losses':0,'win_rate':0,
                    'best_trade':0,'worst_trade':0,'total_pnl':0,'max_drawdown':0}
        pnls   = [t.get('pnl', 0) for t in trades]
        wins   = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        peak = running = max_dd = 0
        for p in pnls:
            running += p
            if running > peak: peak = running
            dd = peak - running
            if dd > max_dd: max_dd = dd
        return {
            'total':        len(trades),
            'wins':         len(wins),
            'losses':       len(losses),
            'win_rate':     round(len(wins)/len(trades)*100, 1) if trades else 0,
            'best_trade':   round(max(pnls), 2) if pnls else 0,
            'worst_trade':  round(min(pnls), 2) if pnls else 0,
            'total_pnl':    round(sum(pnls), 2),
            'max_drawdown': round(max_dd, 2),
        }


# ══════════════════════════════════════════
# FuturesBot
# ══════════════════════════════════════════
class FuturesBot:
    def __init__(self):
        self.ex = ccxt.binance({
            'apiKey':  os.getenv("BINANCE_FUTURES_API_KEY", os.getenv("BINANCE_API_KEY","")).strip(),
            'secret':  os.getenv("BINANCE_FUTURES_SECRET_KEY", os.getenv("BINANCE_SECRET_KEY","")).strip(),
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True,
                'recvWindow': 15000,
                'defaultType': 'future'
            }
        })
        self.ex.set_sandbox_mode(True)
        self.trades:    deque = deque(maxlen=500)
        self.positions: dict  = {}

    async def get_balance(self) -> dict:
        try:
            bal  = self.ex.fetch_balance({'type': 'future'})
            usdt = float(bal['total'].get('USDT', 0.0))
            holdings = {}
            try:
                for p in self.ex.fetch_positions():
                    if not p or float(p.get('contracts', 0) or 0) == 0:
                        continue
                    sym  = p['symbol']
                    ep   = float(p.get('entryPrice', 0) or 0)
                    cp   = float(p.get('markPrice', ep) or ep)
                    side = p.get('side','')
                    upnl = float(p.get('unrealizedPnl', 0) or 0)
                    pct  = ((cp-ep)/ep*100) if ep > 0 else 0
                    if side == 'short': pct = -pct
                    holdings[sym] = {
                        'side':           side,
                        'size':           float(p.get('contracts',0) or 0),
                        'entry_price':    round(ep, 6),
                        'current_price':  round(cp, 6),
                        'unrealized_pnl': round(upnl, 2),
                        'pnl_pct':        round(pct, 2),
                        'leverage':       p.get('leverage', settings['leverage']),
                    }
            except Exception:
                pass
            pnl = usdt - INITIAL_BALANCE
            return {
                'usdt':     round(usdt, 2),
                'total':    round(usdt, 2),
                'pnl':      round(pnl, 2),
                'pnl_pct':  round((pnl / INITIAL_BALANCE) * 100, 2),
                'holdings': holdings,
            }
        except Exception as e:
            log_error(f"Futures balance: {e}", notify=False)
            return {'usdt':0.0,'total':INITIAL_BALANCE,'pnl':0.0,'pnl_pct':0.0,'holdings':{}}

    @staticmethod
    def fix_pair(pair: str) -> str:
        pair = pair.upper().strip().replace("USDTUSDT","USDT").replace(".P","")
        if "/" in pair:           return pair
        if pair.endswith("USDT"): return f"{pair[:-4]}/USDT"
        return f"{pair}/USDT"

    def execute(self, pair: str, direction: str, reason: str = "") -> dict:
        direction = direction.lower().strip()
        pair      = self.fix_pair(pair)
        price = amt = total_val = trade_pnl = 0.0

        try:
            self.ex.load_markets()
            price = float(self.ex.fetch_ticker(pair)['last'])
            try:
                self.ex.set_leverage(settings['leverage'], pair)
            except Exception:
                pass

            val = settings["futures_value"]
            amt = float(self.ex.amount_to_precision(pair, val / price))
            total_val = round(amt * price, 2)

            # alias
            if direction == "buy":   direction = "long_open"
            elif direction == "sell":
                if pair in self.positions and self.positions[pair]['side'] == 'long':
                    direction = "long_close"
                else:
                    direction = "short_open"

            if direction == "long_open":
                self.ex.create_market_buy_order(pair, amt, {'reduceOnly': False})
                self.positions[pair] = {'side':'long','entry':price,'amt':amt}
                msg = f"✅ Long {amt} @ {price:,.4f} × {settings['leverage']}x"
                action_type = "long_open"
                if settings.get("telegram_on_trade"):
                    asyncio.create_task(send_telegram(
                        f"🔵 <b>Long — {pair}</b>\n{amt} @ <code>{price:,.4f}</code> × {settings['leverage']}x"
                    ))

            elif direction == "long_close":
                pos = self.positions.get(pair, {})
                amt = pos.get('amt', amt)
                self.ex.create_market_sell_order(pair, amt, {'reduceOnly': True})
                entry     = pos.get('entry', price)
                trade_pnl = round((price-entry)*amt*settings['leverage'], 2)
                pnl_pct   = round(((price-entry)/entry*100)*settings['leverage'], 2) if entry else 0
                if pair in self.positions: del self.positions[pair]
                update_daily_loss(trade_pnl)
                reason_ar = _reason_ar(reason)
                sign = "+" if trade_pnl >= 0 else ""
                msg = f"✅ إغلاق Long [{reason_ar}] @ {price:,.4f} | PnL: {sign}{trade_pnl}$ ({pnl_pct:+.2f}%)"
                action_type = "long_close"
                if settings.get("telegram_on_trade"):
                    em = "🟢" if trade_pnl >= 0 else "🔴"
                    asyncio.create_task(send_telegram(
                        f"{em} <b>إغلاق Long — {pair}</b>\nPnL: <code>{sign}{trade_pnl}$ ({pnl_pct:+.2f}%)</code>"
                    ))

            elif direction == "short_open":
                self.ex.create_market_sell_order(pair, amt, {'reduceOnly': False})
                self.positions[pair] = {'side':'short','entry':price,'amt':amt}
                msg = f"✅ Short {amt} @ {price:,.4f} × {settings['leverage']}x"
                action_type = "short_open"
                if settings.get("telegram_on_trade"):
                    asyncio.create_task(send_telegram(
                        f"🟣 <b>Short — {pair}</b>\n{amt} @ <code>{price:,.4f}</code> × {settings['leverage']}x"
                    ))

            elif direction == "short_close":
                pos = self.positions.get(pair, {})
                amt = pos.get('amt', amt)
                self.ex.create_market_buy_order(pair, amt, {'reduceOnly': True})
                entry     = pos.get('entry', price)
                trade_pnl = round((entry-price)*amt*settings['leverage'], 2)
                pnl_pct   = round(((entry-price)/entry*100)*settings['leverage'], 2) if entry else 0
                if pair in self.positions: del self.positions[pair]
                update_daily_loss(trade_pnl)
                reason_ar = _reason_ar(reason)
                sign = "+" if trade_pnl >= 0 else ""
                msg = f"✅ إغلاق Short [{reason_ar}] @ {price:,.4f} | PnL: {sign}{trade_pnl}$ ({pnl_pct:+.2f}%)"
                action_type = "short_close"
                if settings.get("telegram_on_trade"):
                    em = "🟢" if trade_pnl >= 0 else "🔴"
                    asyncio.create_task(send_telegram(
                        f"{em} <b>إغلاق Short — {pair}</b>\nPnL: <code>{sign}{trade_pnl}$ ({pnl_pct:+.2f}%)</code>"
                    ))
            else:
                raise Exception(f"أمر غير معروف: {direction}")

            record = _make_record(pair, action_type, "FUTURES", price, amt, total_val, trade_pnl, reason, msg, True)
            self.trades.appendleft(record)
            print(f"💰 [FUTURES] {msg}")
            return record

        except Exception as e:
            err = str(e)
            log_error(f"[FUTURES] {direction} {pair}: {err}")
            record = _make_record(pair, direction, "FUTURES", price, amt, total_val, 0, reason, f"❌ {err[:100]}", False)
            self.trades.appendleft(record)
            return record

    def close_all(self):
        for pair, pos in list(self.positions.items()):
            try:
                if pos['side'] == 'long':
                    self.ex.create_market_sell_order(pair, pos['amt'], {'reduceOnly': True})
                else:
                    self.ex.create_market_buy_order(pair, pos['amt'], {'reduceOnly': True})
                del self.positions[pair]
                print(f"🔴 إغلاق {pos['side']} {pair}")
            except Exception as e:
                log_error(f"Close {pair}: {e}", notify=False)


# ══════════════════════════════════════════
# مساعدات
# ══════════════════════════════════════════
def _reason_ar(r: str) -> str:
    return {"stop_loss":"وقف خسارة 🛑","peak_exit":"ذروة 🎯","trailing_stop":"وقف متحرك 📉"}.get(r, "خروج")

def _make_record(pair, act, market, price, amt, total, pnl, reason, msg, success) -> dict:
    return {
        'id':      int(datetime.now().timestamp() * 1000),
        'time':    datetime.now().strftime("%H:%M:%S"),
        'date':    datetime.now().strftime("%d/%m/%Y"),
        'market':  market,
        'pair':    pair,
        'act':     act,
        'price':   round(price, 6),
        'amount':  round(amt, 6),
        'total':   round(total, 2),
        'pnl':     round(pnl, 2),
        'reason':  reason,
        'st':      msg,
        'success': success,
    }


# ══════════════════════════════════════════
# إنشاء البوتات
# ══════════════════════════════════════════
spot_bot    = SpotBot()
futures_bot = FuturesBot()


# ══════════════════════════════════════════
# أكثر العملات تقلباً
# ══════════════════════════════════════════
async def get_top_movers(limit: int = 10) -> list:
    try:
        tickers = spot_bot.ex.fetch_tickers()
        movers  = []
        for sym, t in tickers.items():
            if not sym.endswith('/USDT'):
                continue
            pct = float(t.get('percentage', 0) or 0)
            vol = float(t.get('quoteVolume', 0) or 0)
            if vol < 500_000:
                continue
            movers.append({
                'symbol':     sym.replace('/USDT',''),
                'price':      t.get('last', 0),
                'change_pct': round(pct, 2),
                'volume_m':   round(vol / 1_000_000, 2),
                'high':       t.get('high', 0),
                'low':        t.get('low', 0),
            })
        movers.sort(key=lambda x: abs(x['change_pct']), reverse=True)
        return movers[:limit]
    except Exception as e:
        log_error(f"Top movers: {e}", notify=False)
        return []


# ══════════════════════════════════════════
# State
# ══════════════════════════════════════════
async def get_full_state() -> dict:
    spot_bal    = await spot_bot.get_balance()
    futures_bal = await futures_bot.get_balance()
    all_trades  = sorted(
        list(spot_bot.trades) + list(futures_bot.trades),
        key=lambda x: x.get('id', 0), reverse=True
    )[:500]
    stats = spot_bot.performance_stats()
    return {
        "spot":       spot_bal,
        "futures":    futures_bal,
        "trades":     all_trades,
        "settings":   {k: v for k, v in settings.items() if k not in ('daily_loss_current','daily_loss_date')},
        "stats":      stats,
        "errors":     list(error_logs)[:50],
        "daily_loss": {
            "current": round(settings["daily_loss_current"], 2),
            "limit":   round(INITIAL_BALANCE * settings["daily_loss_limit_pct"] / 100, 2),
        },
    }


async def broadcast(data: dict):
    dead = []
    for ws in active_connections:
        try:
            await ws.send_json(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in active_connections:
            active_connections.remove(ws)


# ══════════════════════════════════════════
# HTML — SOVEREIGN V7.0
# ══════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SOVEREIGN V7</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;600;700&family=Cairo:wght@300;400;600;700;900&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#030508;--s1:#080c14;--s2:#0c1220;--border:rgba(255,255,255,.055);
  --gold:#d4a017;--gold2:#e8b84b;--gold-dim:rgba(212,160,23,.1);--gold-glow:rgba(212,160,23,.2);
  --green:#00c97a;--green-dim:rgba(0,201,122,.1);
  --red:#e83a3a;--red-dim:rgba(232,58,58,.1);
  --blue:#2eb8e6;--blue-dim:rgba(46,184,230,.1);
  --purple:#9d78f5;--purple-dim:rgba(157,120,245,.1);
  --orange:#f08030;--orange-dim:rgba(240,128,48,.1);
  --text:#c8d4e0;--text2:#7a8fa0;--muted:#3d4f60;
  --mono:'IBM Plex Mono',monospace;--ar:'Cairo',sans-serif;
  --r:10px;--r2:6px;
}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--ar);min-height:100vh;overflow-x:hidden}
body::before{content:'';position:fixed;inset:0;background:
  repeating-linear-gradient(0deg,transparent,transparent 59px,rgba(212,160,23,.012) 60px),
  repeating-linear-gradient(90deg,transparent,transparent 59px,rgba(212,160,23,.012) 60px);
  pointer-events:none;z-index:0}

/* ── Login ─────────────────────────── */
#loginPage{position:fixed;inset:0;background:var(--bg);z-index:999;display:flex;align-items:center;justify-content:center}
.lbox{background:var(--s1);border:1px solid rgba(212,160,23,.18);border-radius:20px;padding:52px 44px;width:360px;text-align:center;position:relative}
.lbox::before{content:'';position:absolute;top:0;left:10%;right:10%;height:1px;background:linear-gradient(90deg,transparent,var(--gold),transparent)}
.llogo{font-family:var(--mono);font-size:26px;font-weight:700;color:var(--gold);letter-spacing:5px;text-shadow:0 0 30px var(--gold-glow)}
.lsub{font-family:var(--mono);font-size:9px;letter-spacing:3px;color:var(--muted);margin:6px 0 38px}
.linput{width:100%;background:rgba(255,255,255,.03);border:1px solid var(--border);border-radius:var(--r2);color:var(--text);font-family:var(--mono);font-size:15px;padding:13px;text-align:center;letter-spacing:6px;outline:none;transition:border-color .2s;margin-bottom:14px}
.linput:focus{border-color:rgba(212,160,23,.35)}
.lbtn{width:100%;background:linear-gradient(135deg,rgba(212,160,23,.18),rgba(212,160,23,.08));border:1px solid rgba(212,160,23,.28);color:var(--gold);font-family:var(--mono);font-size:12px;font-weight:700;padding:13px;border-radius:var(--r2);cursor:pointer;letter-spacing:2px;transition:all .2s}
.lbtn:hover{background:linear-gradient(135deg,rgba(212,160,23,.28),rgba(212,160,23,.14));box-shadow:0 0 24px var(--gold-glow)}
.lerr{color:var(--red);font-family:var(--mono);font-size:11px;margin-top:12px;display:none}

/* ── Wrap ───────────────────────────── */
#dash{display:none}
.wrap{max-width:1440px;margin:0 auto;padding:16px;position:relative;z-index:1}

/* ── Header ─────────────────────────── */
.hdr{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 22px;background:var(--s1);border:1px solid var(--border);border-radius:var(--r);margin-bottom:10px;position:relative;overflow:hidden}
.hdr::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent 0%,var(--gold) 50%,transparent 100%)}
.logo{font-family:var(--mono);font-size:17px;font-weight:700;color:var(--gold);letter-spacing:3px;text-shadow:0 0 16px var(--gold-glow);white-space:nowrap}
.logo span{display:block;font-size:8px;letter-spacing:2px;color:var(--muted);margin-top:2px;font-weight:400}
.hdr-r{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.cbadge{display:flex;align-items:center;gap:5px;padding:5px 11px;border-radius:16px;font-family:var(--mono);font-size:9px;font-weight:700;border:1px solid;transition:all .3s}
.cbadge.on{color:var(--green);border-color:rgba(0,201,122,.28);background:var(--green-dim)}
.cbadge.off{color:var(--red);border-color:rgba(232,58,58,.28);background:var(--red-dim)}
.dot{width:5px;height:5px;border-radius:50%;background:currentColor;animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}
.sbadge{padding:5px 12px;border-radius:16px;font-family:var(--mono);font-size:9px;font-weight:700;border:1px solid;white-space:nowrap}
.s-on{background:var(--green-dim);color:var(--green);border-color:rgba(0,201,122,.28)}
.s-pause{background:rgba(240,200,48,.08);color:#f0c830;border-color:rgba(240,200,48,.22)}
.s-emer{background:var(--red-dim);color:var(--red);border-color:rgba(232,58,58,.35);animation:ep 1s infinite}
.s-cal{background:var(--orange-dim);color:var(--orange);border-color:rgba(240,128,48,.28)}
@keyframes ep{0%,100%{opacity:1}50%{opacity:.3}}

/* ── Ticker ─────────────────────────── */
.ticker{background:var(--s1);border:1px solid var(--border);border-radius:var(--r2);padding:7px 16px;margin-bottom:10px;font-family:var(--mono);font-size:10px;color:var(--muted);display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.tlive{color:var(--gold);font-weight:700;background:var(--gold-dim);padding:2px 8px;border-radius:3px}
.tsep{color:var(--border)}

/* ── Tabs ───────────────────────────── */
.tabs{display:flex;gap:3px;padding:5px;background:var(--s1);border:1px solid var(--border);border-radius:var(--r);margin-bottom:10px}
.tab{flex:1;padding:9px 6px;border-radius:var(--r2);font-family:var(--ar);font-size:11px;font-weight:600;cursor:pointer;border:none;background:transparent;color:var(--muted);transition:all .2s;text-align:center}
.tab.active{background:var(--gold-dim);color:var(--gold);border:1px solid rgba(212,160,23,.2)}
.tab:hover:not(.active){background:rgba(255,255,255,.03);color:var(--text2)}
.panel{display:none}
.panel.active{display:block}

/* ── Actions Bar ────────────────────── */
.abar{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:10px;align-items:center}
.btn{padding:8px 14px;border-radius:var(--r2);font-family:var(--ar);font-size:11px;font-weight:700;cursor:pointer;border:1px solid;transition:all .18s;display:inline-flex;align-items:center;gap:5px;white-space:nowrap;line-height:1}
.btn:active{transform:scale(.97)}
.bg{background:var(--green-dim);color:var(--green);border-color:rgba(0,201,122,.28)}
.bg:hover{background:rgba(0,201,122,.18)}
.by{background:rgba(240,200,48,.07);color:#f0c830;border-color:rgba(240,200,48,.22)}
.by:hover{background:rgba(240,200,48,.14)}
.br{background:var(--red-dim);color:var(--red);border-color:rgba(232,58,58,.28)}
.br:hover{background:rgba(232,58,58,.18)}
.bb{background:var(--blue-dim);color:var(--blue);border-color:rgba(46,184,230,.28)}
.bb:hover{background:rgba(46,184,230,.18)}
.bo{background:var(--gold-dim);color:var(--gold);border-color:rgba(212,160,23,.28)}
.bo:hover{background:rgba(212,160,23,.18)}
.bx{background:rgba(255,255,255,.03);color:var(--muted);border-color:var(--border)}

/* ── Balance Grid ───────────────────── */
.bg2{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
@media(max-width:700px){.bg2{grid-template-columns:1fr}}
.bpanel{background:var(--s1);border:1px solid var(--border);border-radius:var(--r);padding:16px;position:relative;overflow:hidden}
.bpanel.spot{border-color:rgba(46,184,230,.12)}
.bpanel.fut{border-color:rgba(157,120,245,.12)}
.bpanel::before{content:'';position:absolute;top:0;left:0;right:0;height:1px}
.bpanel.spot::before{background:linear-gradient(90deg,transparent,var(--blue),transparent)}
.bpanel.fut::before{background:linear-gradient(90deg,transparent,var(--purple),transparent)}
.ptitle{font-family:var(--mono);font-size:9px;font-weight:700;letter-spacing:2px;text-transform:uppercase;margin-bottom:14px;display:flex;align-items:center;gap:7px}
.spot .ptitle{color:var(--blue)}
.fut .ptitle{color:var(--purple)}
.ptag{padding:2px 7px;border-radius:3px;font-size:8px;font-family:var(--mono);font-weight:700}
.stag{background:var(--blue-dim);color:var(--blue);border:1px solid rgba(46,184,230,.18)}
.ftag{background:var(--purple-dim);color:var(--purple);border:1px solid rgba(157,120,245,.18)}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.metric .lbl{font-size:8px;color:var(--muted);font-family:var(--mono);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}
.metric .val{font-family:var(--mono);font-size:19px;font-weight:700;line-height:1}
.metric .sub{font-size:9px;color:var(--muted);font-family:var(--mono);margin-top:3px}
.cg{color:var(--gold)} .cgr{color:var(--green)} .cr{color:var(--red)} .cb{color:var(--blue)} .cp{color:var(--purple)} .cm{color:var(--muted)} .co{color:var(--orange)}

/* ── Daily Loss Bar ─────────────────── */
.dlbar-wrap{margin-top:12px}
.dlbar-row{display:flex;justify-content:space-between;font-family:var(--mono);font-size:9px;color:var(--muted);margin-bottom:4px}
.dlbar{height:3px;background:rgba(255,255,255,.05);border-radius:2px;overflow:hidden}
.dlbar-fill{height:100%;border-radius:2px;transition:width .6s,background .4s}

/* ── Stats Grid ─────────────────────── */
.sgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px}
@media(max-width:900px){.sgrid{grid-template-columns:repeat(2,1fr)}}
.scard{background:var(--s1);border:1px solid var(--border);border-radius:var(--r);padding:14px;position:relative;overflow:hidden}
.scard .si{position:absolute;top:10px;left:10px;font-size:22px;opacity:.06}
.scard .sl{font-size:8px;color:var(--muted);font-family:var(--mono);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:7px}
.scard .sv{font-family:var(--mono);font-size:20px;font-weight:700;line-height:1}
.scard .ss{font-size:9px;color:var(--muted);font-family:var(--mono);margin-top:4px}

/* ── Futures Holdings ───────────────── */
.fh-wrap{margin-top:12px}
.fh-title{font-size:8px;color:var(--muted);font-family:var(--mono);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:6px}
.fh-table{width:100%;font-family:var(--mono);font-size:10px;border-collapse:collapse}
.fh-table th{font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;padding:4px 6px;text-align:right;border-bottom:1px solid var(--border)}
.fh-table td{padding:6px;text-align:right;border-bottom:1px solid rgba(255,255,255,.02)}

/* ── Section ────────────────────────── */
.section{background:var(--s1);border:1px solid var(--border);border-radius:var(--r);overflow:hidden;margin-bottom:10px}
.sh{padding:12px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.sh-title{font-size:9px;font-family:var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:2px}
.ctag{font-family:var(--mono);font-size:9px;color:var(--gold);background:var(--gold-dim);padding:2px 9px;border-radius:12px}

/* ── Table ──────────────────────────── */
table{width:100%;border-collapse:collapse}
thead th{padding:9px 14px;font-size:8px;font-family:var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:1.5px;text-align:right;background:rgba(255,255,255,.018);border-bottom:1px solid var(--border)}
tbody tr{border-bottom:1px solid rgba(255,255,255,.022);transition:background .15s}
tbody tr:hover{background:rgba(255,255,255,.018)}
tbody tr.flash{animation:rf 1.6s ease-out}
@keyframes rf{0%{background:rgba(212,160,23,.12)}100%{background:transparent}}
td{padding:10px 14px;font-size:11px;text-align:right;vertical-align:middle}
.tm{font-family:var(--mono)}
.tmuted{color:var(--muted);font-size:9px;font-family:var(--mono)}
.tpair{font-family:var(--mono);font-weight:700;font-size:12px}
.tprice{font-family:var(--mono);color:var(--gold)}

/* ── Badges ─────────────────────────── */
.badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:4px;font-family:var(--mono);font-size:8px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;white-space:nowrap}
.bbuy{background:var(--green-dim);color:var(--green);border:1px solid rgba(0,201,122,.18)}
.bsell{background:var(--red-dim);color:var(--red);border:1px solid rgba(232,58,58,.18)}
.blong{background:var(--blue-dim);color:var(--blue);border:1px solid rgba(46,184,230,.18)}
.blclose{background:rgba(46,184,230,.04);color:var(--blue);border:1px solid rgba(46,184,230,.1)}
.bshort{background:var(--purple-dim);color:var(--purple);border:1px solid rgba(157,120,245,.18)}
.bsclose{background:rgba(157,120,245,.04);color:var(--purple);border:1px solid rgba(157,120,245,.1)}
.mkt-s{background:var(--blue-dim);color:var(--blue);font-family:var(--mono);font-size:7px;padding:2px 5px;border-radius:3px;font-weight:700}
.mkt-f{background:var(--purple-dim);color:var(--purple);font-family:var(--mono);font-size:7px;padding:2px 5px;border-radius:3px;font-weight:700}

/* ── PnL Colors ─────────────────────── */
.pp{color:var(--green);font-family:var(--mono);font-weight:700}
.pn{color:var(--red);font-family:var(--mono);font-weight:700}
.pz{color:var(--muted);font-family:var(--mono)}

/* ── Settings Panel ─────────────────── */
.sgp{background:var(--s1);border:1px solid var(--border);border-radius:var(--r);padding:16px 20px;margin-bottom:10px}
.sgp-title{font-family:var(--mono);font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:2px;margin-bottom:14px}
.sgrid2{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
.sgrp{background:var(--s2);border:1px solid var(--border);border-radius:var(--r2);padding:14px}
.sgrp-title{font-size:10px;color:var(--text2);font-family:var(--mono);margin-bottom:12px;display:flex;align-items:center;gap:6px;font-weight:600}
.srow{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px}
.srow:last-child{margin-bottom:0}
.slabel{font-size:11px;color:var(--text2);font-family:var(--ar)}
.toggle{position:relative;display:inline-block;width:38px;height:20px;flex-shrink:0}
.toggle input{opacity:0;width:0;height:0}
.tslider{position:absolute;cursor:pointer;inset:0;background:var(--s1);border:1px solid var(--border);border-radius:20px;transition:.28s}
.tslider:before{position:absolute;content:"";height:14px;width:14px;left:2px;bottom:2px;background:var(--muted);border-radius:50%;transition:.28s}
.toggle input:checked+.tslider{background:var(--green-dim);border-color:rgba(0,201,122,.35)}
.toggle input:checked+.tslider:before{transform:translateX(18px);background:var(--green)}
.ninput{background:rgba(255,255,255,.04);border:1px solid var(--border);color:var(--gold);font-family:var(--mono);font-size:11px;font-weight:600;width:68px;padding:5px 7px;border-radius:5px;text-align:center;outline:none}
.ninput:focus{border-color:rgba(212,160,23,.35)}
.ninput[type=time]{width:82px}
.sinput{background:rgba(255,255,255,.04);border:1px solid var(--border);color:var(--text);font-family:var(--mono);font-size:10px;padding:5px 7px;border-radius:5px;cursor:pointer;outline:none}
.sinput:focus{border-color:rgba(212,160,23,.35)}

/* ── Movers ─────────────────────────── */
.mgrid{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:10px}
@media(max-width:1000px){.mgrid{grid-template-columns:repeat(3,1fr)}}
@media(max-width:600px){.mgrid{grid-template-columns:repeat(2,1fr)}}
.mcard{background:var(--s1);border:1px solid var(--border);border-radius:var(--r2);padding:14px;text-align:center;transition:border-color .2s}
.mcard:hover{border-color:rgba(212,160,23,.2)}
.msym{font-family:var(--mono);font-size:13px;font-weight:700;color:var(--text);margin-bottom:5px}
.mpct{font-family:var(--mono);font-size:15px;font-weight:700}
.mvol{font-size:9px;color:var(--muted);font-family:var(--mono);margin-top:3px}

/* ── Calendar Card ──────────────────── */
.cal-card{background:var(--s1);border:1px solid rgba(240,128,48,.18);border-radius:var(--r);padding:14px;margin-bottom:10px}
.cal-row{display:flex;align-items:center;gap:10px;padding:10px;background:var(--orange-dim);border-radius:var(--r2)}
.cal-dot{width:7px;height:7px;border-radius:50%;background:var(--orange);animation:blink 1.5s infinite;flex-shrink:0}

/* ── Error Log ──────────────────────── */
.eitem{display:flex;align-items:flex-start;gap:10px;padding:10px 16px;border-bottom:1px solid rgba(255,255,255,.025)}
.etime{color:var(--muted);font-family:var(--mono);font-size:9px;white-space:nowrap;margin-top:1px}
.emsg{color:var(--red);font-family:var(--mono);font-size:11px;flex:1;word-break:break-all}

/* ── Portfolio Table ────────────────── */
.port-table{width:100%;border-collapse:collapse}
.port-table th{padding:9px 14px;font-size:8px;font-family:var(--mono);color:var(--muted);text-transform:uppercase;letter-spacing:1.5px;text-align:right;background:rgba(255,255,255,.018);border-bottom:1px solid var(--border)}
.port-table td{padding:12px 14px;text-align:right;border-bottom:1px solid rgba(255,255,255,.022);font-family:var(--mono);font-size:12px}
.port-table tr:hover td{background:rgba(255,255,255,.018)}

/* ── Empty ───────────────────────────── */
.empty{padding:50px;text-align:center;color:var(--muted);font-family:var(--mono);font-size:12px}
.empty-i{font-size:32px;display:block;margin-bottom:10px;opacity:.18}

/* ── Modal ───────────────────────────── */
.modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:500;align-items:center;justify-content:center;padding:20px}
.modal.open{display:flex}
.mbox{background:var(--s1);border:1px solid rgba(212,160,23,.14);border-radius:16px;padding:28px;max-width:460px;width:100%;max-height:85vh;overflow-y:auto;position:relative}
.mbox::before{content:'';position:absolute;top:0;left:10%;right:10%;height:1px;background:linear-gradient(90deg,transparent,var(--gold),transparent)}
.mtitle{font-family:var(--mono);color:var(--gold);font-weight:700;letter-spacing:2px;font-size:12px;margin-bottom:18px}
.mclose{position:absolute;top:14px;left:18px;background:none;border:none;color:var(--muted);cursor:pointer;font-size:18px;line-height:1;transition:color .2s}
.mclose:hover{color:var(--text)}

/* ── Scrollbar ───────────────────────── */
::-webkit-scrollbar{width:3px;height:3px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}

/* ── Mobile ──────────────────────────── */
@media(max-width:600px){
  .wrap{padding:10px}
  .hdr{padding:12px 14px}
  .logo{font-size:14px;letter-spacing:2px}
  .metrics{grid-template-columns:repeat(3,1fr)}
  .metric .val{font-size:15px}
  .sgrid{grid-template-columns:1fr 1fr}
  table{font-size:10px}
  td,thead th{padding:7px 10px}
  .tabs .tab{font-size:10px;padding:8px 4px}
}
</style>
</head>
<body>

<!-- ═══ LOGIN ═══════════════════════════════════ -->
<div id="loginPage">
  <div class="lbox">
    <div class="llogo">SOVEREIGN</div>
    <div class="lsub">TRADING SYSTEM · V7.0 · TESTNET</div>
    <input id="pwInput" class="linput" type="password" placeholder="••••••••" onkeydown="if(event.key==='Enter')doLogin()">
    <button class="lbtn" onclick="doLogin()">ENTER →</button>
    <div class="lerr" id="loginErr">❌ كلمة السر غير صحيحة</div>
  </div>
</div>

<!-- ═══ DASHBOARD ════════════════════════════════ -->
<div id="dash">
<div class="wrap">

<!-- Header -->
<div class="hdr">
  <div class="logo">SOVEREIGN<span>SPOT + FUTURES SYSTEM · V7.0 · TESTNET</span></div>
  <div class="hdr-r">
    <span id="stateBadge" class="sbadge s-on">⏳ تحميل</span>
    <div id="connBadge" class="cbadge off"><div class="dot"></div><span id="connTxt">جاري الاتصال...</span></div>
  </div>
</div>

<!-- Ticker -->
<div class="ticker">
  <span class="tlive">⚡ LIVE</span>
  <span id="clock">--:--:--</span>
  <span class="tsep">|</span>
  <span>آخر تحديث: <span id="lastUpd" style="color:var(--text)">--</span></span>
  <span class="tsep">|</span>
  <span id="calTicker" style="color:var(--orange);display:none"></span>
  <span class="tsep" id="calSep" style="display:none">|</span>
  <span>خسارة اليوم: <span id="dlTicker" class="cm">--</span></span>
</div>

<!-- Tabs -->
<div class="tabs">
  <button class="tab active" onclick="goTab('main',this)">🏠 الرئيسية</button>
  <button class="tab" onclick="goTab('portfolio',this)">💼 المحفظة</button>
  <button class="tab" onclick="goTab('settings',this)">⚙️ الإعدادات</button>
  <button class="tab" onclick="goTab('movers',this)">🔥 المتقلبة</button>
  <button class="tab" onclick="goTab('errors',this)">🗂️ السجلات</button>
</div>

<!-- ══ TAB: MAIN ════════════════════════════════ -->
<div id="tab-main" class="panel active">

  <!-- Actions -->
  <div class="abar">
    <button class="btn by" id="toggleBtn" onclick="toggleBot()">⏸ إيقاف</button>
    <button class="btn br" id="eBtn" onclick="emergencyStop()">🚨 طوارئ</button>
    <button class="btn bg" id="rBtn" style="display:none" onclick="resume()">▶ استئناف</button>
    <div style="width:1px;height:22px;background:var(--border)"></div>
    <button class="btn br" onclick="liqSpot()">⚠ تصفية Spot</button>
    <button class="btn br" onclick="liqFut()">⚠ إغلاق Futures</button>
    <div style="width:1px;height:22px;background:var(--border)"></div>
    <button class="btn bo" onclick="openExcel()">📊 Excel</button>
    <button class="btn bb" onclick="goTab('movers',document.querySelectorAll('.tab')[3]);loadMovers()">🔥 المتقلبة</button>
  </div>

  <!-- Balance -->
  <div class="bg2">
    <!-- Spot -->
    <div class="bpanel spot">
      <div class="ptitle">💧 SPOT <span class="ptag stag">Testnet</span></div>
      <div class="metrics">
        <div class="metric"><div class="lbl">إجمالي المحفظة</div><div class="val cg" id="sTot">--</div><div class="sub">USDT</div></div>
        <div class="metric"><div class="lbl">USDT الحر</div><div class="val cb" id="sUsd">--</div><div class="sub">متاح</div></div>
        <div class="metric"><div class="lbl">PnL</div><div class="val" id="sPnl">--</div><div class="sub" id="sPnlPct">--</div></div>
      </div>
      <div class="dlbar-wrap">
        <div class="dlbar-row"><span>حد الخسارة اليومي</span><span id="dlText" class="cm">--</span></div>
        <div class="dlbar"><div id="dlFill" class="dlbar-fill" style="width:0%;background:var(--green)"></div></div>
      </div>
    </div>
    <!-- Futures -->
    <div class="bpanel fut">
      <div class="ptitle">⚡ FUTURES <span class="ptag ftag">× <span id="levDisp">--</span></span></div>
      <div class="metrics">
        <div class="metric"><div class="lbl">الرصيد</div><div class="val cg" id="fTot">--</div><div class="sub">USDT</div></div>
        <div class="metric"><div class="lbl">مراكز</div><div class="val cp" id="fPos">0</div><div class="sub">مفتوحة</div></div>
        <div class="metric"><div class="lbl">PnL</div><div class="val" id="fPnl">--</div><div class="sub" id="fPnlPct">--</div></div>
      </div>
      <div id="fHoldings" class="fh-wrap"></div>
    </div>
  </div>

  <!-- Stats -->
  <div class="sgrid">
    <div class="scard"><div class="si">📊</div><div class="sl">إجمالي الصفقات</div><div class="sv cg" id="stTotal">0</div><div class="ss">صفقة منذ البداية</div></div>
    <div class="scard"><div class="si">🎯</div><div class="sl">Win Rate</div><div class="sv cgr" id="stWR">0%</div><div class="ss" id="stWL">0 ✅ 0 ❌</div></div>
    <div class="scard"><div class="si">🏆</div><div class="sl">أفضل صفقة</div><div class="sv cgr" id="stBest">--</div><div class="ss">ربح محقق</div></div>
    <div class="scard"><div class="si">📉</div><div class="sl">Max Drawdown</div><div class="sv cr" id="stDD">--</div><div class="ss">أقصى تراجع</div></div>
  </div>

  <!-- Trades -->
  <div class="section">
    <div class="sh">
      <span class="sh-title">📋 سجل الصفقات</span>
      <span class="ctag" id="trCount">0 صفقة</span>
    </div>
    <div style="overflow-x:auto">
      <table>
        <thead><tr>
          <th>التاريخ</th><th>الوقت</th><th>سوق</th><th>الزوج</th>
          <th>النوع</th><th>الكمية</th><th>السعر</th>
          <th>الإجمالي</th><th>PnL $</th><th>PnL %</th><th>السبب</th>
        </tr></thead>
        <tbody id="tBody"><tr><td colspan="11"><div class="empty"><span class="empty-i">📡</span>في انتظار الإشارات...</div></td></tr></tbody>
      </table>
    </div>
  </div>
</div><!-- /tab-main -->

<!-- ══ TAB: PORTFOLIO ═══════════════════════════ -->
<div id="tab-portfolio" class="panel">
  <div class="section">
    <div class="sh">
      <span class="sh-title">💼 عملاتي الحالية</span>
      <span class="ctag" id="portCount">0 عملة</span>
    </div>
    <div style="overflow-x:auto">
      <table class="port-table">
        <thead><tr>
          <th>العملة</th><th>الكمية</th><th>سعر الشراء</th>
          <th>السعر الحالي</th><th>القيمة $</th><th>PnL $</th><th>PnL %</th>
        </tr></thead>
        <tbody id="portBody"><tr><td colspan="7"><div class="empty"><span class="empty-i">💼</span>لا توجد عملات</div></td></tr></tbody>
      </table>
    </div>
  </div>
</div>

<!-- ══ TAB: SETTINGS ════════════════════════════ -->
<div id="tab-settings" class="panel">
  <div class="sgp">
    <div class="sgp-title">⚙️ إعدادات النظام الكاملة — كل ميزة قابلة للتفعيل والإلغاء</div>
    <div class="sgrid2">

      <!-- Spot -->
      <div class="sgrp">
        <div class="sgrp-title">💧 Spot</div>
        <div class="srow"><span class="slabel">وضع الشراء</span>
          <select class="sinput" id="sBuyMode" onchange="ss('spot_buy_mode',this.value)">
            <option value="fixed">ثابت $</option>
            <option value="percent">نسبة %</option>
          </select>
        </div>
        <div class="srow"><span class="slabel">قيمة الشراء</span><input class="ninput" id="sBuyVal" type="number" min="11" onchange="ss('spot_buy_value',+this.value)"></div>
        <div class="srow"><span class="slabel">نسبة البيع (1=100%)</span><input class="ninput" id="sSellR" type="number" min="0.1" max="1" step="0.1" onchange="ss('spot_sell_ratio',+this.value)"></div>
      </div>

      <!-- Futures -->
      <div class="sgrp">
        <div class="sgrp-title">⚡ Futures</div>
        <div class="srow"><span class="slabel">تفعيل Futures</span><label class="toggle"><input type="checkbox" id="futEn" onchange="ss('futures_enabled',this.checked)"><span class="tslider"></span></label></div>
        <div class="srow"><span class="slabel">حجم المركز $</span><input class="ninput" id="fVal" type="number" min="11" onchange="ss('futures_value',+this.value)"></div>
        <div class="srow"><span class="slabel">الرافعة المالية ×</span><input class="ninput" id="levIn" type="number" min="1" max="125" onchange="ss('leverage',+this.value)"></div>
      </div>

      <!-- Risk Management -->
      <div class="sgrp">
        <div class="sgrp-title">🛡️ Risk Management</div>
        <div class="srow"><span class="slabel">تفعيل</span><label class="toggle"><input type="checkbox" id="riskEn" onchange="ss('risk_enabled',this.checked)"><span class="tslider"></span></label></div>
        <div class="srow"><span class="slabel">Trailing Stop %</span><input class="ninput" id="trailPct" type="number" min="0.1" max="20" step="0.1" onchange="ss('trailing_stop_pct',+this.value)"></div>
        <div class="srow"><span class="slabel">Fixed Stop Loss %</span><input class="ninput" id="fslPct" type="number" min="0.1" max="50" step="0.1" onchange="ss('fixed_stop_loss_pct',+this.value)"></div>
      </div>

      <!-- Daily Loss Limit -->
      <div class="sgrp">
        <div class="sgrp-title">🛡️ حد الخسارة اليومي</div>
        <div class="srow"><span class="slabel">تفعيل</span><label class="toggle"><input type="checkbox" id="dlEn" onchange="ss('daily_loss_enabled',this.checked)"><span class="tslider"></span></label></div>
        <div class="srow"><span class="slabel">الحد الأقصى %</span><input class="ninput" id="dlPct" type="number" min="0.5" max="50" step="0.5" onchange="ss('daily_loss_limit_pct',+this.value)"></div>
      </div>

      <!-- Session Manager -->
      <div class="sgrp">
        <div class="sgrp-title">⏰ Session Manager</div>
        <div class="srow"><span class="slabel">تفعيل</span><label class="toggle"><input type="checkbox" id="sessEn" onchange="ss('session_enabled',this.checked)"><span class="tslider"></span></label></div>
        <div class="srow"><span class="slabel">بداية الجلسة</span><input class="ninput" id="sessS" type="time" onchange="ss('session_start',this.value)"></div>
        <div class="srow"><span class="slabel">نهاية الجلسة</span><input class="ninput" id="sessE" type="time" onchange="ss('session_end',this.value)"></div>
      </div>

      <!-- Economic Calendar -->
      <div class="sgrp">
        <div class="sgrp-title">📅 التقويم الاقتصادي</div>
        <div class="srow"><span class="slabel">تفعيل</span><label class="toggle"><input type="checkbox" id="calEn" onchange="ss('calendar_enabled',this.checked)"><span class="tslider"></span></label></div>
        <div class="srow"><span class="slabel">إيقاف قبل (دقيقة)</span><input class="ninput" id="calB" type="number" min="5" max="120" onchange="ss('calendar_pause_before',+this.value)"></div>
        <div class="srow"><span class="slabel">استئناف بعد (دقيقة)</span><input class="ninput" id="calA" type="number" min="5" max="180" onchange="ss('calendar_resume_after',+this.value)"></div>
      </div>

      <!-- Telegram -->
      <div class="sgrp">
        <div class="sgrp-title">📲 Telegram</div>
        <div class="srow"><span class="slabel">تفعيل الإشعارات</span><label class="toggle"><input type="checkbox" id="tgEn" onchange="ss('telegram_enabled',this.checked)"><span class="tslider"></span></label></div>
        <div class="srow"><span class="slabel">إشعار عند كل صفقة</span><label class="toggle"><input type="checkbox" id="tgTrade" onchange="ss('telegram_on_trade',this.checked)"><span class="tslider"></span></label></div>
        <div class="srow"><span class="slabel">إشعار عند الأخطاء</span><label class="toggle"><input type="checkbox" id="tgErr" onchange="ss('telegram_on_error',this.checked)"><span class="tslider"></span></label></div>
        <div class="srow"><span class="slabel">تقرير يومي</span><label class="toggle"><input type="checkbox" id="tgRep" onchange="ss('telegram_daily_report',this.checked)"><span class="tslider"></span></label></div>
        <div class="srow"><span class="slabel">وقت التقرير</span><input class="ninput" id="tgTime" type="time" onchange="ss('telegram_report_time',this.value)"></div>
      </div>

    </div>
  </div>
</div>

<!-- ══ TAB: MOVERS ══════════════════════════════ -->
<div id="tab-movers" class="panel">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
    <span style="font-family:var(--mono);font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:2px">🔥 أكثر العملات تقلباً — 24 ساعة</span>
    <button class="btn bb" onclick="loadMovers()">🔄 تحديث</button>
  </div>
  <div class="mgrid" id="moversGrid">
    <div class="empty" style="grid-column:1/-1"><span class="empty-i">🔥</span>اضغط تحديث</div>
  </div>
</div>

<!-- ══ TAB: ERRORS ══════════════════════════════ -->
<div id="tab-errors" class="panel">
  <div class="section">
    <div class="sh">
      <span class="sh-title">🗂️ سجل الأخطاء</span>
      <button class="btn bx" onclick="clearErr()" style="font-size:10px;padding:4px 10px">مسح الكل</button>
    </div>
    <div id="errList"><div class="empty"><span class="empty-i">✅</span>لا توجد أخطاء</div></div>
  </div>
</div>

</div><!-- /wrap -->
</div><!-- /dash -->

<!-- ══ MODAL: EXCEL ════════════════════════════ -->
<div id="excelModal" class="modal">
  <div class="mbox" style="max-width:360px;text-align:center">
    <button class="mclose" onclick="closeModal('excelModal')">✕</button>
    <div class="mtitle">📊 تصدير Excel</div>
    <p style="color:var(--text2);font-size:13px;font-family:var(--ar);margin-bottom:20px;line-height:1.6">سيتم تحميل ملف Excel كامل بجميع بيانات الصفقات مع التواريخ والأسعار والأرباح والخسائر</p>
    <button class="btn bo" style="width:100%;justify-content:center;font-size:13px;padding:12px" onclick="doExport()">⬇ تحميل الملف</button>
  </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<script>
// ══════════════════════════
// LOGIN
// ══════════════════════════
function doLogin(){
  const pw=document.getElementById('pwInput').value.trim();
  if(!pw) return;
  fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})})
    .then(r=>r.json()).then(d=>{
      if(d.ok){
        sessionStorage.setItem('sv7','1');
        showDash();
      } else {
        const err=document.getElementById('loginErr');
        err.style.display='block';
        document.getElementById('pwInput').value='';
        setTimeout(()=>err.style.display='none',3000);
      }
    }).catch(()=>{showDash();}); // dev fallback
}

function showDash(){
  document.getElementById('loginPage').style.display='none';
  document.getElementById('dash').style.display='block';
  connect();
}

if(sessionStorage.getItem('sv7')==='1') showDash();

// ══════════════════════════
// WEBSOCKET
// ══════════════════════════
let wsDelay=2000, seenIds=new Set(), lastData=null;

function connect(){
  const proto=location.protocol==='https:'?'wss:':'ws:';
  const ws=new WebSocket(proto+'//'+location.host+'/ws');
  ws.onopen=()=>{
    document.getElementById('connBadge').className='cbadge on';
    document.getElementById('connTxt').textContent='متصل · LIVE';
    wsDelay=2000;
  };
  ws.onmessage=e=>{lastData=JSON.parse(e.data);render(lastData);};
  ws.onclose=()=>{
    document.getElementById('connBadge').className='cbadge off';
    document.getElementById('connTxt').textContent='انقطع الاتصال...';
    setTimeout(connect,wsDelay);
    wsDelay=Math.min(wsDelay*1.5,30000);
  };
  ws.onerror=()=>ws.close();
}

// ══════════════════════════
// HELPERS
// ══════════════════════════
function fmt(n,d=2){return Number(n||0).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});}
function pc(v){return v>0?'pp':v<0?'pn':'pz';}
function sg(v){return v>0?'+':'';}
function pnlHtml(v,pct){
  if(v===0&&pct===0) return '<span class="pz">—</span>';
  const c=pc(v);
  const pctHtml=pct!==undefined?` <span style="font-size:10px">(${sg(pct)}${pct}%)</span>`:'';
  return `<span class="${c}">${sg(v)}${fmt(v)}$${pctHtml}</span>`;
}

// ══════════════════════════
// RENDER
// ══════════════════════════
function render(d){
  const now=new Date();
  document.getElementById('clock').textContent=now.toLocaleTimeString('ar-SA');
  document.getElementById('lastUpd').textContent=now.toLocaleTimeString('ar-SA');

  const s=d.settings||{};
  syncSettings(s);
  renderStateBadge(s);

  // Spot
  const sp=d.spot||{};
  document.getElementById('sTot').textContent=fmt(sp.total);
  document.getElementById('sUsd').textContent=fmt(sp.usdt);
  const spPnl=sp.pnl||0, spPct=sp.pnl_pct||0;
  const spEl=document.getElementById('sPnl');
  spEl.textContent=sg(spPnl)+fmt(spPnl)+'$';
  spEl.className='val '+pc(spPnl);
  document.getElementById('sPnlPct').textContent=sg(spPnl)+spPct+'%';

  // Daily Loss Bar
  const dl=d.daily_loss||{};
  const cur=Math.abs(dl.current||0), lim=dl.limit||1;
  const dlPct=Math.min((cur/lim)*100,100);
  document.getElementById('dlText').textContent=`${fmt(cur)}$ / ${fmt(lim)}$`;
  document.getElementById('dlTicker').textContent=`${fmt(cur)}$ / ${fmt(lim)}$`;
  const fill=document.getElementById('dlFill');
  fill.style.width=dlPct+'%';
  fill.style.background=dlPct>80?'var(--red)':dlPct>50?'var(--orange)':'var(--green)';

  // Futures
  const fp=d.futures||{};
  document.getElementById('fTot').textContent=fmt(fp.total);
  document.getElementById('fPos').textContent=Object.keys(fp.holdings||{}).length;
  const fpPnl=fp.pnl||0;
  const fpEl=document.getElementById('fPnl');
  fpEl.textContent=sg(fpPnl)+fmt(fpPnl)+'$';
  fpEl.className='val '+pc(fpPnl);
  document.getElementById('fPnlPct').textContent=sg(fpPnl)+(fp.pnl_pct||0)+'%';
  document.getElementById('levDisp').textContent=(s.leverage||'--')+'x';

  // Futures Positions
  const fh=fp.holdings||{};
  const fhEl=document.getElementById('fHoldings');
  if(Object.keys(fh).length){
    fhEl.innerHTML=`<div class="fh-title">مراكز مفتوحة</div>
      <table class="fh-table">
        <thead><tr><th>الزوج</th><th>الجانب</th><th>دخول</th><th>الحالي</th><th>PnL $</th><th>PnL %</th></tr></thead>
        <tbody>${Object.entries(fh).map(([sym,p])=>`
          <tr>
            <td style="font-weight:700">${sym}</td>
            <td><span class="badge ${p.side==='long'?'blong':'bshort'}">${p.side==='long'?'LONG':'SHORT'}</span></td>
            <td>${fmt(p.entry_price,4)}</td>
            <td style="color:var(--blue)">${fmt(p.current_price,4)}</td>
            <td class="${pc(p.unrealized_pnl)}">${sg(p.unrealized_pnl)}${fmt(p.unrealized_pnl)}$</td>
            <td class="${pc(p.pnl_pct)}">${sg(p.pnl_pct)}${p.pnl_pct}%</td>
          </tr>`).join('')}</tbody>
      </table>`;
  } else {
    fhEl.innerHTML='';
  }

  // Calendar Ticker
  const calEv=s.calendar_next_event||'';
  const calT=document.getElementById('calTicker');
  const calSep=document.getElementById('calSep');
  if(calEv && s.calendar_enabled){
    calT.textContent=`${calEv} — ${s.calendar_next_event_time}`;
    calT.style.display='';calSep.style.display='';
  } else {
    calT.style.display='none';calSep.style.display='none';
  }

  // Stats
  const st=d.stats||{};
  document.getElementById('stTotal').textContent=st.total||0;
  document.getElementById('stWR').textContent=(st.win_rate||0)+'%';
  document.getElementById('stWL').textContent=`${st.wins||0} ✅  ${st.losses||0} ❌`;
  const best=document.getElementById('stBest');
  best.textContent=(st.best_trade>0?'+':'')+fmt(st.best_trade||0)+'$';
  best.className='sv '+pc(st.best_trade||0);
  document.getElementById('stDD').textContent='-'+fmt(st.max_drawdown||0)+'$';
  document.getElementById('trCount').textContent=(st.total||0)+' صفقة';

  // Portfolio
  renderPortfolio(sp.holdings||{});
  // Trades
  renderTrades(d.trades||[]);
  // Errors
  renderErrors(d.errors||[]);
}

// ── Portfolio ─────────────────────────────
function renderPortfolio(h){
  const keys=Object.keys(h);
  document.getElementById('portCount').textContent=keys.length+' عملة';
  if(!keys.length){
    document.getElementById('portBody').innerHTML='<tr><td colspan="7"><div class="empty"><span class="empty-i">💼</span>لا توجد عملات محتفظ بها</div></td></tr>';
    return;
  }
  document.getElementById('portBody').innerHTML=keys.map(c=>{
    const v=h[c];
    return `<tr>
      <td><span style="color:var(--gold);font-weight:700">${c}</span></td>
      <td>${v.amount}</td>
      <td>${fmt(v.buy_price,4)}</td>
      <td style="color:var(--blue)">${fmt(v.current_price,4)}</td>
      <td style="color:var(--gold)">${fmt(v.value,2)}$</td>
      <td class="${pc(v.pnl_usd)}">${sg(v.pnl_usd)}${fmt(v.pnl_usd,2)}$</td>
      <td class="${pc(v.pnl_pct)}">${sg(v.pnl_pct)}${v.pnl_pct}%</td>
    </tr>`;
  }).join('');
}

// ── Trades ────────────────────────────────
const badgeMap={
  buy:'<span class="badge bbuy">شراء</span>',
  sell:'<span class="badge bsell">بيع</span>',
  long_open:'<span class="badge blong">LONG ▲</span>',
  long_close:'<span class="badge blclose">↓ Long</span>',
  short_open:'<span class="badge bshort">SHORT ▼</span>',
  short_close:'<span class="badge bsclose">↑ Short</span>',
};
const reasonMap={stop_loss:'🛑 SL',peak_exit:'🎯 Peak',trailing_stop:'📉 Trail'};

function renderTrades(trades){
  if(!trades.length){
    document.getElementById('tBody').innerHTML='<tr><td colspan="11"><div class="empty"><span class="empty-i">📡</span>في انتظار الإشارات...</div></td></tr>';
    return;
  }
  document.getElementById('tBody').innerHTML=trades.map(x=>{
    const isNew=!seenIds.has(x.id); if(isNew) seenIds.add(x.id);
    const mkt=x.market==='FUTURES'?'<span class="mkt-f">F</span>':'<span class="mkt-s">S</span>';
    const badge=badgeMap[x.act]||`<span class="badge bsell">${x.act}</span>`;
    const isSell=['sell','long_close','short_close'].includes(x.act);
    const pnlUsd=isSell&&x.pnl!==0?`<span class="${pc(x.pnl)}">${sg(x.pnl)}${fmt(x.pnl,2)}$</span>`:'<span class="pz">—</span>';
    let pnlPct='<span class="pz">—</span>';
    if(isSell&&x.pnl!==0&&x.total>0){
      const cost=(x.total||0)-(x.pnl||0);
      if(cost>0){const pp=(x.pnl/cost)*100;pnlPct=`<span class="${pc(pp)}">${sg(pp)}${fmt(pp,2)}%</span>`;}
    }
    return `<tr class="${isNew?'flash':''}">
      <td class="tmuted">${x.date||'--'}</td>
      <td class="tmuted">${x.time}</td>
      <td>${mkt}</td>
      <td class="tpair">${x.pair}</td>
      <td>${badge}</td>
      <td class="tm">${x.amount>0?x.amount:'—'}</td>
      <td class="tprice">${x.price>0?fmt(x.price,4):'—'}</td>
      <td class="tm cg">${x.total>0?fmt(x.total,2)+'$':'—'}</td>
      <td>${pnlUsd}</td>
      <td>${pnlPct}</td>
      <td class="tmuted">${reasonMap[x.reason]||'—'}</td>
    </tr>`;
  }).join('');
}

// ── Errors ────────────────────────────────
function renderErrors(errs){
  const el=document.getElementById('errList');
  if(!errs.length){el.innerHTML='<div class="empty"><span class="empty-i">✅</span>لا توجد أخطاء</div>';return;}
  el.innerHTML=errs.map(e=>`<div class="eitem"><span class="etime">${e.date} ${e.time}</span><span class="emsg">❌ ${e.msg}</span></div>`).join('');
}

// ── State Badge ───────────────────────────
function renderStateBadge(s){
  const b=document.getElementById('stateBadge');
  const tBtn=document.getElementById('toggleBtn');
  const eBtn=document.getElementById('eBtn');
  const rBtn=document.getElementById('rBtn');
  if(s.emergency_stop){
    b.textContent='🚨 طوارئ';b.className='sbadge s-emer';
    tBtn.style.display='none';eBtn.style.display='none';rBtn.style.display='inline-flex';
  } else if(s.calendar_paused){
    b.textContent='📅 إيقاف — حدث اقتصادي';b.className='sbadge s-cal';
    tBtn.textContent='⏸ مؤقف';tBtn.className='btn bx';
    tBtn.style.display='inline-flex';eBtn.style.display='inline-flex';rBtn.style.display='none';
  } else if(!s.active){
    b.textContent='⏸ متوقف';b.className='sbadge s-pause';
    tBtn.textContent='▶ تشغيل';tBtn.className='btn bg';
    tBtn.style.display='inline-flex';eBtn.style.display='inline-flex';rBtn.style.display='none';
  } else {
    b.textContent='✅ نشط';b.className='sbadge s-on';
    tBtn.textContent='⏸ إيقاف';tBtn.className='btn by';
    tBtn.style.display='inline-flex';eBtn.style.display='inline-flex';rBtn.style.display='none';
  }
}

// ══════════════════════════
// SETTINGS SYNC
// ══════════════════════════
function syncSettings(s){
  const set=(id,v)=>{const el=document.getElementById(id);if(!el)return;el.type==='checkbox'?el.checked=!!v:el.value=v;};
  set('sBuyMode',s.spot_buy_mode);set('sBuyVal',s.spot_buy_value);set('sSellR',s.spot_sell_ratio);
  set('futEn',s.futures_enabled);set('fVal',s.futures_value);set('levIn',s.leverage);
  set('riskEn',s.risk_enabled);set('trailPct',s.trailing_stop_pct);set('fslPct',s.fixed_stop_loss_pct);
  set('dlEn',s.daily_loss_enabled);set('dlPct',s.daily_loss_limit_pct);
  set('sessEn',s.session_enabled);set('sessS',s.session_start);set('sessE',s.session_end);
  set('calEn',s.calendar_enabled);set('calB',s.calendar_pause_before);set('calA',s.calendar_resume_after);
  set('tgEn',s.telegram_enabled);set('tgTrade',s.telegram_on_trade);
  set('tgErr',s.telegram_on_error);set('tgRep',s.telegram_daily_report);set('tgTime',s.telegram_report_time);
}

// ══════════════════════════
// CONTROLS
// ══════════════════════════
async function api(url,body){
  const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  return r.json();
}
async function toggleBot(){await api('/control/toggle');}
async function emergencyStop(){
  if(!confirm('🚨 إيقاف الطوارئ!\nسيوقف البوت ويبيع جميع المراكز فوراً.\n\nمتأكد؟'))return;
  await api('/control/emergency');
}
async function resume(){await api('/control/resume');}
async function liqSpot(){if(!confirm('تصفية جميع مراكز Spot؟'))return;await api('/liquidate');}
async function liqFut(){if(!confirm('إغلاق جميع مراكز Futures؟'))return;await api('/liquidate/futures');}
async function clearErr(){await api('/errors/clear');}
async function ss(key,val){await api('/settings/update',{key,value:val});}

// ══════════════════════════
// TABS
// ══════════════════════════
function goTab(name,btn){
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  if(btn) btn.classList.add('active');
  const p=document.getElementById('tab-'+name);
  if(p) p.classList.add('active');
  if(name==='movers') loadMovers();
}

// ══════════════════════════
// MOVERS
// ══════════════════════════
async function loadMovers(){
  document.getElementById('moversGrid').innerHTML='<div class="empty" style="grid-column:1/-1"><span class="empty-i" style="opacity:.5">⏳</span>جاري التحميل...</div>';
  const data=await fetch('/movers').then(r=>r.json()).catch(()=>[]);
  if(!data.length){
    document.getElementById('moversGrid').innerHTML='<div class="empty" style="grid-column:1/-1"><span class="empty-i">⚠️</span>لا توجد بيانات</div>';
    return;
  }
  document.getElementById('moversGrid').innerHTML=data.map(m=>`
    <div class="mcard">
      <div class="msym">${m.symbol}</div>
      <div class="mpct ${m.change_pct>=0?'cgr':'cr'}">${m.change_pct>=0?'+':''}${m.change_pct}%</div>
      <div class="mvol">${fmt(m.price,4)} USDT</div>
      <div class="mvol">${m.volume_m}M Vol</div>
    </div>`).join('');
}

// ══════════════════════════
// EXCEL
// ══════════════════════════
function openExcel(){document.getElementById('excelModal').classList.add('open');}
function closeModal(id){document.getElementById(id).classList.remove('open');}

function doExport(){
  if(!lastData?.trades?.length){alert('لا توجد صفقات للتصدير');return;}
  const rows=lastData.trades.map(t=>({
    'التاريخ':          t.date||'',
    'الوقت':            t.time||'',
    'السوق':            t.market||'',
    'الزوج':            t.pair||'',
    'نوع الأمر':        t.act||'',
    'الكمية':           t.amount||0,
    'سعر التنفيذ':      t.price||0,
    'الإجمالي $':       t.total||0,
    'PnL $':            t.pnl||0,
    'السبب':            t.reason||'',
    'الحالة':           t.success?'ناجح':'فاشل',
    'التفاصيل':         t.st||'',
  }));
  const ws=XLSX.utils.json_to_sheet(rows);
  // تنسيق عرض الأعمدة
  ws['!cols']=[{wch:12},{wch:10},{wch:8},{wch:12},{wch:12},{wch:10},{wch:12},{wch:10},{wch:10},{wch:14},{wch:8},{wch:40}];
  const wb=XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb,'Trades',ws);
  const d=new Date().toLocaleDateString('en-GB').replace(/\//g,'-');
  XLSX.writeFile(wb,`SOVEREIGN_V7_Trades_${d}.xlsx`);
  closeModal('excelModal');
}

// Clock
setInterval(()=>{const e=document.getElementById('clock');if(e)e.textContent=new Date().toLocaleTimeString('ar-SA');},1000);
</script>
</body>
</html>"""


# ══════════════════════════════════════════
# Models
# ══════════════════════════════════════════
class Signal(BaseModel):
    pair:      str
    direction: str
    reason:    Optional[str] = None
    market:    Optional[str] = None

class AuthReq(BaseModel):
    password: str

class SettingReq(BaseModel):
    key:   str
    value: object


# ══════════════════════════════════════════
# Routes
# ══════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
async def root():
    return HTML


@app.post("/auth/login")
async def auth_login(req: AuthReq):
    return {"ok": req.password == DASHBOARD_PASSWORD}


@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    active_connections.append(ws)
    print(f"🔌 +1 | total={len(active_connections)}")
    try:
        await ws.send_json(await get_full_state())
        while True:
            await asyncio.sleep(5)
            await ws.send_json(await get_full_state())
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if ws in active_connections:
            active_connections.remove(ws)
        print(f"🔌 -1 | total={len(active_connections)}")


@app.post("/webhook")
async def webhook(s: Signal):
    # ── فحوصات الأمان ─────────────────────
    if settings.get("emergency_stop"):
        return {"status":"emergency_stop","ok":False}

    if not settings.get("active"):
        return {"status":"inactive","ok":False}

    ok_sess, sess_msg = is_session_active()
    if not ok_sess:
        return {"status":"outside_session","message":sess_msg,"ok":False}

    ok_cal, cal_msg = is_calendar_paused()
    if ok_cal:
        return {"status":"calendar_paused","event":cal_msg,"ok":False}

    # ── توجيه الأمر ───────────────────────
    direction = s.direction.lower().strip()
    reason    = s.reason or ""
    market    = (s.market or "spot").lower()

    if direction in ("long_open","long_close","short_open","short_close"):
        market = "futures"

    if market == "futures":
        if not settings.get("futures_enabled"):
            return {"status":"futures_disabled","ok":False}
        result = futures_bot.execute(s.pair, direction, reason)
    else:
        result = spot_bot.execute(s.pair, direction, reason)

    await broadcast(await get_full_state())
    return result


@app.post("/settings/update")
async def update_setting(req: SettingReq):
    if req.key in settings:
        settings[req.key] = req.value
        print(f"⚙️ {req.key} ← {req.value}")
    await broadcast(await get_full_state())
    return {"ok": True}


@app.post("/control/toggle")
async def ctrl_toggle():
    if not settings.get("emergency_stop"):
        settings["active"] = not settings["active"]
    await broadcast(await get_full_state())
    return {"active": settings["active"]}


@app.post("/control/emergency")
async def ctrl_emergency():
    settings["emergency_stop"] = True
    settings["active"]         = False
    spot_bot.liquidate_all()
    futures_bot.close_all()
    await send_telegram("🚨 <b>إيقاف طوارئ</b>\nتم تصفية جميع المراكز فوراً.")
    await broadcast(await get_full_state())
    return {"ok": True}


@app.post("/control/resume")
async def ctrl_resume():
    settings["emergency_stop"] = False
    settings["active"]         = True
    await send_telegram("▶️ <b>استئناف التداول</b>")
    await broadcast(await get_full_state())
    return {"ok": True}


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


@app.post("/errors/clear")
async def clear_errors():
    error_logs.clear()
    await broadcast(await get_full_state())
    return {"ok": True}


@app.get("/movers")
async def movers_endpoint():
    return await get_top_movers()


@app.get("/portfolio")
async def portfolio_endpoint():
    return await get_full_state()


@app.get("/health")
async def health():
    return {
        "status":         "ok",
        "version":        "7.0.0",
        "active":         settings["active"],
        "emergency_stop": settings["emergency_stop"],
        "spot_trades":    len(spot_bot.trades),
        "futures_trades": len(futures_bot.trades),
        "connections":    len(active_connections),
        "leverage":       settings["leverage"],
    }


# ══════════════════════════════════════════
# Background Tasks
# ══════════════════════════════════════════
@app.on_event("startup")
async def on_startup():
    asyncio.create_task(background_loop())


async def background_loop():
    last_report_date = ""
    while True:
        try:
            await asyncio.sleep(60)

            # ── التقويم الاقتصادي ──────────
            if settings.get("calendar_enabled"):
                await fetch_economic_calendar()

            # ── التقرير اليومي Telegram ────
            if (settings.get("telegram_daily_report")
                    and settings.get("telegram_enabled")):
                now_str  = datetime.now().strftime("%H:%M")
                today_str = datetime.now().strftime("%Y-%m-%d")
                if now_str == settings.get("telegram_report_time","00:00") and last_report_date != today_str:
                    last_report_date = today_str
                    st  = spot_bot.performance_stats()
                    bal = await spot_bot.get_balance()
                    sign = "+" if st['total_pnl'] >= 0 else ""
                    await send_telegram(
                        f"📊 <b>التقرير اليومي — {datetime.now().strftime('%d/%m/%Y')}</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━\n"
                        f"الصفقات:  {st['total']} | ✅ {st['wins']} | ❌ {st['losses']}\n"
                        f"Win Rate: {st['win_rate']}%\n"
                        f"PnL اليوم: {sign}{st['total_pnl']:.2f}$\n"
                        f"Max DD:   -{st['max_drawdown']:.2f}$\n"
                        f"المحفظة:  {bal['total']:,.2f}$\n"
                        f"━━━━━━━━━━━━━━━━━━━"
                    )
        except Exception as e:
            print(f"⚠️ Background: {e}")


# ══════════════════════════════════════════
# Entry Point
# ══════════════════════════════════════════
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

