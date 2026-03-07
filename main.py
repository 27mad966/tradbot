"""
╔══════════════════════════════════════════════════════════════════╗
║           SOVEREIGN TRADING SYSTEM — V8.0                       ║
║           Spot + Futures | Advanced Analytics | Full Dashboard  ║
║           Built with FastAPI + CCXT + WebSocket                 ║
╚══════════════════════════════════════════════════════════════════╝

Environment Variables (Render):
  BINANCE_API_KEY              ← Spot API Key
  BINANCE_SECRET_KEY           ← Spot Secret
  BINANCE_FUTURES_API_KEY      ← Futures API Key (optional)
  BINANCE_FUTURES_SECRET_KEY   ← Futures Secret (optional)
  DASHBOARD_PASSWORD           ← Dashboard password (default: sovereign2025)
  INITIAL_BALANCE              ← Starting capital (default: 10000)
  TELEGRAM_TOKEN               ← Telegram bot token (optional)
  TELEGRAM_CHAT_ID             ← Telegram chat ID (optional)
"""

import os, asyncio, ccxt, uvicorn, json, math
from datetime import datetime, timedelta
from collections import deque
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import httpx

# ══════════════════════════════════════════
# App Init
# ══════════════════════════════════════════
app = FastAPI(title="SOVEREIGN V8.0", version="8.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ══════════════════════════════════════════
# Config
# ══════════════════════════════════════════
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "sovereign2025")
INITIAL_BALANCE    = float(os.getenv("INITIAL_BALANCE", "10000"))
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

settings = {
    "active":                   True,
    "emergency_stop":           False,
    # Spot
    "spot_buy_mode":            "fixed",
    "spot_buy_value":           100.0,
    "spot_sell_ratio":          1.0,
    "spot_max_positions":       5,
    # Futures
    "futures_enabled":          True,
    "futures_mode":             "fixed",
    "futures_value":            100.0,
    "leverage":                 10,
    "futures_max_positions":    3,
    # Risk
    "risk_enabled":             True,
    "trailing_stop_pct":        1.2,
    "fixed_stop_loss_pct":      3.0,
    # Position Sizing
    "position_sizing_enabled":  False,
    "position_sizing_pct":      5.0,
    "max_concentration_pct":    20.0,
    # Daily Loss
    "daily_loss_enabled":       True,
    "daily_loss_limit_pct":     5.0,
    "daily_loss_current":       0.0,
    "daily_loss_date":          "",
    # Session
    "session_enabled":          False,
    "session_start":            "08:00",
    "session_end":              "22:00",
    # Calendar
    "calendar_enabled":         False,
    "calendar_pause_before":    30,
    "calendar_resume_after":    60,
    "calendar_paused":          False,
    "calendar_next_event":      "",
    "calendar_next_event_time": "",
    # Telegram
    "telegram_enabled":         bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID),
    "telegram_on_trade":        True,
    "telegram_on_error":        True,
    "telegram_daily_report":    True,
    "telegram_report_time":     "00:00",
    # Notifications
    "sound_enabled":            True,
    "toast_enabled":            True,
    # Report period
    "report_hours":             24,
}

active_connections: list[WebSocket] = []
error_logs:   deque = deque(maxlen=200)
login_logs:   deque = deque(maxlen=100)
equity_curve:  deque = deque(maxlen=2000)   # {ts, value}
toast_queue:   deque = deque(maxlen=20)
trade_pairs:   deque = deque(maxlen=500)    # matched buy+sell records
open_trades:   dict  = {}                   # pair -> open trade record


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
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "date": datetime.now().strftime("%d/%m"), "msg": msg}
    error_logs.appendleft(entry)
    print(f"❌ {msg}")
    if notify and settings.get("telegram_on_error"):
        asyncio.create_task(send_telegram(f"⚠️ <b>Alert</b>\n{msg[:200]}"))


def add_toast(msg: str, kind: str = "info"):
    toast_queue.appendleft({"msg": msg, "kind": kind, "ts": int(datetime.now().timestamp() * 1000)})


# ══════════════════════════════════════════
# Safety Checks
# ══════════════════════════════════════════
def is_session_active() -> tuple[bool, str]:
    if not settings.get("session_enabled"):
        return True, ""
    now = datetime.now().strftime("%H:%M")
    s, e = settings["session_start"], settings["session_end"]
    return (True, "") if s <= now <= e else (False, f"Outside session ({s}–{e})")


def is_calendar_paused() -> tuple[bool, str]:
    if not settings.get("calendar_enabled"):
        return False, ""
    if settings.get("calendar_paused"):
        return True, settings.get("calendar_next_event", "Economic Event")
    return False, ""


def update_daily_loss(pnl: float) -> bool:
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
            add_toast("🚨 Daily loss limit reached — Bot stopped!", "error")
            asyncio.create_task(send_telegram(
                f"🚨 <b>Auto Stop</b>\nDaily loss limit hit!\n"
                f"Loss: {settings['daily_loss_current']:.2f}$\n"
                f"Limit: {abs(limit):.2f}$"
            ))
            return True
    return False


# ══════════════════════════════════════════
# Economic Calendar
# ══════════════════════════════════════════
async def fetch_economic_calendar():
    if not settings.get("calendar_enabled"):
        return
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp   = await client.get("https://nfs.faireconomy.media/ff_calendar_thisweek.json")
            events = resp.json()
        now      = datetime.now()
        upcoming = []
        for ev in events:
            if ev.get("impact") not in ["High"]:
                continue
            try:
                dt_str  = ev["date"].replace("Z", "+00:00")
                ev_time = datetime.fromisoformat(dt_str).replace(tzinfo=None)
                if ev_time > now:
                    upcoming.append({"time": ev_time, "title": ev.get("title",""), "country": ev.get("country","")})
            except:
                continue
        if not upcoming:
            settings["calendar_next_event"] = ""
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
                add_toast(f"⏸ Paused — {nxt['title']}", "warning")
                await send_telegram(f"⏸ <b>Paused — Economic Event</b>\n{nxt['country']}: {nxt['title']}")
        else:
            if settings["calendar_paused"]:
                settings["calendar_paused"] = False
                add_toast("▶️ Trading resumed", "success")
                await send_telegram("▶️ <b>Trading Resumed</b> ✅")
    except Exception as e:
        log_error(f"Calendar: {e}", notify=False)


# ══════════════════════════════════════════
# Analytics Engine
# ══════════════════════════════════════════
def calc_advanced_stats(trades: list) -> dict:
    closed = [t for t in trades if t.get("act") in ("sell","long_close","short_close") and t.get("success")]
    if not closed:
        return {
            "total":0,"wins":0,"losses":0,"win_rate":0,
            "best_trade":0,"worst_trade":0,"total_pnl":0,
            "max_drawdown":0,"profit_factor":0,
            "sharpe":0,"avg_win":0,"avg_loss":0,
            "avg_duration_min":0,"consecutive_wins":0,"consecutive_losses":0,
            "expectancy":0,
        }
    pnls   = [t.get("pnl",0) for t in closed]
    wins   = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    # Drawdown
    peak = running = max_dd = 0
    for p in pnls:
        running += p
        if running > peak: peak = running
        dd = peak - running
        if dd > max_dd: max_dd = dd

    # Profit Factor
    gross_profit = sum(wins) if wins else 0
    gross_loss   = abs(sum(losses)) if losses else 0
    pf = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (999 if gross_profit > 0 else 0)

    # Sharpe (simplified, daily returns)
    if len(pnls) > 1:
        avg  = sum(pnls) / len(pnls)
        std  = math.sqrt(sum((p - avg)**2 for p in pnls) / len(pnls))
        sharpe = round((avg / std) * math.sqrt(252), 2) if std > 0 else 0
    else:
        sharpe = 0

    # Consecutive
    max_cw = max_cl = cur_cw = cur_cl = 0
    for p in pnls:
        if p > 0: cur_cw += 1; cur_cl = 0
        else:     cur_cl += 1; cur_cw = 0
        max_cw = max(max_cw, cur_cw)
        max_cl = max(max_cl, cur_cl)

    avg_win  = round(sum(wins)   / len(wins), 2)   if wins   else 0
    avg_loss = round(sum(losses) / len(losses), 2) if losses else 0
    wr       = len(wins) / len(closed)
    expectancy = round(wr * avg_win + (1 - wr) * avg_loss, 2)

    return {
        "total":               len(closed),
        "wins":                len(wins),
        "losses":              len(losses),
        "win_rate":            round(wr * 100, 1),
        "best_trade":          round(max(pnls), 2),
        "worst_trade":         round(min(pnls), 2),
        "total_pnl":           round(sum(pnls), 2),
        "max_drawdown":        round(max_dd, 2),
        "profit_factor":       pf,
        "sharpe":              sharpe,
        "avg_win":             avg_win,
        "avg_loss":            avg_loss,
        "consecutive_wins":    max_cw,
        "consecutive_losses":  max_cl,
        "expectancy":          expectancy,
        "gross_profit":        round(gross_profit, 2),
        "gross_loss":          round(gross_loss, 2),
    }


def get_period_stats(trades: list, hours: int) -> dict:
    cutoff = datetime.now() - timedelta(hours=hours)
    period = []
    for t in trades:
        try:
            dt = datetime.strptime(f"{t.get('date','01/01/2024')} {t.get('time','00:00:00')}", "%d/%m/%Y %H:%M:%S")
            if dt >= cutoff:
                period.append(t)
        except:
            pass
    closed = [t for t in period if t.get("act") in ("sell","long_close","short_close") and t.get("success")]
    pnls   = [t.get("pnl",0) for t in closed]
    wins   = [p for p in pnls if p > 0]
    return {
        "trades":   len(closed),
        "wins":     len(wins),
        "losses":   len(closed) - len(wins),
        "pnl":      round(sum(pnls), 2),
        "win_rate": round(len(wins)/len(closed)*100, 1) if closed else 0,
    }


# ══════════════════════════════════════════
# SpotBot
# ══════════════════════════════════════════
class SpotBot:
    def __init__(self):
        self.ex = ccxt.binance({
            "apiKey":  os.getenv("BINANCE_API_KEY","").strip(),
            "secret":  os.getenv("BINANCE_SECRET_KEY","").strip(),
            "enableRateLimit": True,
            "options": {"adjustForTimeDifference": True, "recvWindow": 15000, "defaultType": "spot"}
        })
        self.ex.set_sandbox_mode(True)
        self.trades:      deque = deque(maxlen=1000)
        self.buy_prices:  dict  = {}
        self.buy_amounts: dict  = {}
        self.buy_times:   dict  = {}

    async def get_balance(self) -> dict:
        try:
            bal   = self.ex.fetch_balance()
            usdt  = float(bal["total"].get("USDT", 0.0))
            pv    = usdt
            holdings = {}
            for coin, raw in bal["total"].items():
                amt = float(raw or 0)
                if coin in ("USDT","BUSD","USDC","TUSD","DAI") or amt < 0.000001:
                    continue
                try:
                    ticker = self.ex.fetch_ticker(f"{coin}/USDT")
                    price  = float(ticker["last"])
                    value  = amt * price
                    pv    += value
                    buy_p  = self.buy_prices.get(coin, price)
                    pnl_u  = (price - buy_p) * amt
                    pnl_p  = ((price - buy_p) / buy_p * 100) if buy_p > 0 else 0
                    holdings[coin] = {
                        "amount":        round(amt, 6),
                        "buy_price":     round(buy_p, 6),
                        "current_price": round(price, 6),
                        "value":         round(value, 2),
                        "pnl_usd":       round(pnl_u, 2),
                        "pnl_pct":       round(pnl_p, 2),
                    }
                except:
                    pass
            for coin, buy_p in self.buy_prices.items():
                if coin in holdings:
                    continue
                try:
                    ticker = self.ex.fetch_ticker(f"{coin}/USDT")
                    price  = float(ticker["last"])
                    amt    = self.buy_amounts.get(coin, 0.0)
                    if amt < 0.000001:
                        continue
                    value  = amt * price
                    pv    += value
                    pnl_u  = (price - buy_p) * amt
                    pnl_p  = ((price - buy_p) / buy_p * 100) if buy_p > 0 else 0
                    holdings[coin] = {
                        "amount":        round(amt, 6),
                        "buy_price":     round(buy_p, 6),
                        "current_price": round(price, 6),
                        "value":         round(value, 2),
                        "pnl_usd":       round(pnl_u, 2),
                        "pnl_pct":       round(pnl_p, 2),
                    }
                except:
                    pass
            total_pnl = pv - INITIAL_BALANCE
            return {
                "usdt":     round(usdt, 2),
                "total":    round(pv, 2),
                "pnl":      round(total_pnl, 2),
                "pnl_pct":  round((total_pnl / INITIAL_BALANCE) * 100, 2) if INITIAL_BALANCE else 0,
                "holdings": holdings,
            }
        except Exception as e:
            log_error(f"Spot balance: {e}", notify=False)
            return {"usdt":0,"total":INITIAL_BALANCE,"pnl":0,"pnl_pct":0,"holdings":{}}

    @staticmethod
    def fix_pair(p: str) -> str:
        p = p.upper().strip().replace("USDTUSDT","USDT").replace(".P","")
        if "/" in p: return p
        if p.endswith("USDT"): return f"{p[:-4]}/USDT"
        return f"{p}/USDT"

    def _place_risk_orders(self, pair: str, amt: float, buy_price: float):
        if not settings.get("risk_enabled"):
            return
        # إلغاء أوامر Algo المفتوحة أولاً لتجنب MAX_NUM_ALGO_ORDERS
        try:
            open_orders = self.ex.fetch_open_orders(pair)
            for o in open_orders:
                otype = str(o.get("type","")).lower()
                if any(x in otype for x in ("stop","trailing","algo")):
                    try:
                        self.ex.cancel_order(o["id"], pair)
                    except:
                        pass
        except Exception as e:
            log_error(f"Cancel orders ({pair}): {e}", notify=False)
        # وضع Stop Loss الجديد
        try:
            sl = round(buy_price * (1 - settings["fixed_stop_loss_pct"] / 100), 6)
            self.ex.create_order(pair, "stop_loss_limit", "sell", amt, sl, {"stopPrice": sl})
        except Exception as e:
            log_error(f"SL failed ({pair}): {e}", notify=False)
        try:
            self.ex.create_order(pair, "trailing_stop_market", "sell", amt, None, {
                "callbackRate": settings["trailing_stop_pct"]
            })
        except:
            pass

    def execute(self, pair: str, side: str, reason: str = "") -> dict:
        side  = side.lower().strip()
        pair  = self.fix_pair(pair)
        coin  = pair.split("/")[0]
        price = amt = total_val = trade_pnl = 0.0
        action_type = side
        try:
            self.ex.load_markets()
            ticker = self.ex.fetch_ticker(pair)
            price  = float(ticker["last"])
            if side in ("buy","long_open"):
                # Position sizing
                bal  = self.ex.fetch_balance()
                usdt = float(bal["total"].get("USDT", 0.0))
                if settings.get("position_sizing_enabled"):
                    val = usdt * (settings["position_sizing_pct"] / 100)
                elif settings["spot_buy_mode"] == "fixed":
                    val = settings["spot_buy_value"]
                else:
                    val = usdt * (settings["spot_buy_value"] / 100)
                val = max(val, 11.0)
                if val > usdt:
                    raise Exception(f"Insufficient balance ({usdt:.2f}$ < {val:.2f}$)")
                # Max concentration check
                if settings.get("position_sizing_enabled"):
                    total_portfolio = usdt + sum(
                        self.buy_amounts.get(c, 0) * price for c in self.buy_prices
                    )
                    concentration = (val / total_portfolio * 100) if total_portfolio > 0 else 0
                    if concentration > settings.get("max_concentration_pct", 20):
                        raise Exception(f"Concentration limit: {concentration:.1f}% > {settings['max_concentration_pct']}%")
                amt       = float(self.ex.amount_to_precision(pair, val / price))
                total_val = round(amt * price, 2)
                self.ex.create_market_buy_order(pair, amt)
                self.buy_prices[coin]  = price
                self.buy_amounts[coin] = amt
                self.buy_times[coin]   = datetime.now()
                self._place_risk_orders(pair, amt, price)
                action_type = "buy"
                record_trade_pair(pair, "buy", "SPOT", price, amt, total_val, 0, "")
                add_toast(f"🟢 BUY {coin} @ {price:,.4f}", "success")
                if settings.get("telegram_on_trade"):
                    asyncio.create_task(send_telegram(
                        f"🟢 <b>BUY — {coin}/USDT</b>\n"
                        f"💰 Entry: <code>{price:,.4f}$</code>\n"
                        f"📦 Amount: <code>{amt}</code>\n"
                        f"💵 Total: <code>{total_val}$</code>"
                    ))
            elif side in ("sell","long_close"):
                # ─── جلب الرصيد الحقيقي من Binance مباشرة ───
                # المحاولة 1: fetch_balance
                bal   = self.ex.fetch_balance()
                c_bal = float(bal["total"].get(coin, 0.0))
                # المحاولة 2: free balance فقط (أكثر دقة)
                if c_bal < 0.000001:
                    c_bal = float(bal.get("free", {}).get(coin, 0.0))
                # المحاولة 3: من الذاكرة الداخلية (fallback)
                if c_bal < 0.000001:
                    c_bal = self.buy_amounts.get(coin, 0.0)
                # المحاولة 4: إعادة جلب بعد تأخير (Testnet lag)
                if c_bal < 0.000001:
                    import time; time.sleep(1.5)
                    bal2  = self.ex.fetch_balance()
                    c_bal = float(bal2["total"].get(coin, 0.0))
                if c_bal < 0.000001:
                    raise Exception(f"No {coin} balance — tried 4 methods")
                amt       = float(self.ex.amount_to_precision(pair, c_bal * settings["spot_sell_ratio"]))
                total_val = round(amt * price, 2)
                # إلغاء أوامر Stop/Algo المفتوحة قبل البيع (تحرير الرصيد المحجوز)
                try:
                    open_orders = self.ex.fetch_open_orders(pair)
                    for o in open_orders:
                        try: self.ex.cancel_order(o["id"], pair)
                        except: pass
                except: pass
                self.ex.create_market_sell_order(pair, amt)
                buy_p     = self.buy_prices.get(coin, price)
                trade_pnl = round((price - buy_p) * amt, 2)
                pnl_pct   = round(((price - buy_p) / buy_p * 100), 2) if buy_p > 0 else 0
                # Duration
                buy_time = self.buy_times.get(coin)
                duration_min = round((datetime.now() - buy_time).total_seconds() / 60, 1) if buy_time else 0
                if coin in self.buy_prices:  del self.buy_prices[coin]
                if coin in self.buy_amounts: del self.buy_amounts[coin]
                if coin in self.buy_times:   del self.buy_times[coin]
                update_daily_loss(trade_pnl)
                action_type = "sell"
                record_trade_pair(pair, "sell", "SPOT", price, amt, total_val, trade_pnl, reason)
                em   = "🟢" if trade_pnl >= 0 else "🔴"
                sign = "+" if trade_pnl >= 0 else ""
                add_toast(f"{em} SELL {coin}: {sign}{trade_pnl}$", "success" if trade_pnl >= 0 else "error")
                if settings.get("telegram_on_trade"):
                    asyncio.create_task(send_telegram(
                        f"{em} <b>SELL — {coin}/USDT</b>\n"
                        f"📌 Reason: {_reason_en(reason)}\n"
                        f"🔵 Entry: <code>{buy_p:,.4f}$</code>\n"
                        f"🔴 Exit: <code>{price:,.4f}$</code>\n"
                        f"📊 PnL: <code>{sign}{trade_pnl}$ ({pnl_pct:+.2f}%)</code>\n"
                        f"⏱ Duration: {duration_min}min"
                    ))
                # Equity curve snapshot
                equity_curve.append({"ts": int(datetime.now().timestamp() * 1000), "delta": trade_pnl})
            else:
                raise Exception(f"Unknown order: {side}")

            record = _make_record(pair, action_type, "SPOT", price, amt, total_val, trade_pnl, reason, True)
            self.trades.appendleft(record)
            return record
        except Exception as e:
            log_error(f"[SPOT] {side} {pair}: {e}")
            record = _make_record(pair, side, "SPOT", price, amt, total_val, 0, reason, False, str(e)[:100])
            self.trades.appendleft(record)
            return record

    def liquidate_all(self):
        try:
            bal = self.ex.fetch_balance()
            for coin, raw in bal["total"].items():
                amt = float(raw or 0)
                if coin in ("USDT","BUSD","USDC","TUSD","DAI") or amt < 0.000001:
                    continue
                try:
                    self.ex.load_markets()
                    pair = f"{coin}/USDT"
                    if pair in self.ex.markets:
                        self.ex.create_market_sell_order(pair, amt)
                except Exception as e:
                    log_error(f"Liquidate {coin}: {e}", notify=False)
        except Exception as e:
            log_error(f"Liquidate all: {e}", notify=False)


# ══════════════════════════════════════════
# FuturesBot
# ══════════════════════════════════════════
class FuturesBot:
    def __init__(self):
        self.ex = ccxt.binance({
            "apiKey":  os.getenv("BINANCE_FUTURES_API_KEY", os.getenv("BINANCE_API_KEY","")).strip(),
            "secret":  os.getenv("BINANCE_FUTURES_SECRET_KEY", os.getenv("BINANCE_SECRET_KEY","")).strip(),
            "enableRateLimit": True,
            "options": {"adjustForTimeDifference": True, "recvWindow": 15000, "defaultType": "future"}
        })
        self.trades:     deque = deque(maxlen=1000)
        self.positions:  dict  = {}
        self.open_times: dict  = {}

    async def get_balance(self) -> dict:
        try:
            bal  = self.ex.fetch_balance({"type":"future"})
            usdt = float(bal["total"].get("USDT", 0.0))
            holdings = {}
            try:
                for p in self.ex.fetch_positions():
                    if not p or float(p.get("contracts",0) or 0) == 0:
                        continue
                    sym  = p["symbol"]
                    ep   = float(p.get("entryPrice",0) or 0)
                    cp   = float(p.get("markPrice", ep) or ep)
                    side = p.get("side","")
                    upnl = float(p.get("unrealizedPnl",0) or 0)
                    pct  = ((cp-ep)/ep*100) if ep > 0 else 0
                    if side == "short": pct = -pct
                    holdings[sym] = {
                        "side":           side,
                        "size":           float(p.get("contracts",0) or 0),
                        "entry_price":    round(ep,6),
                        "current_price":  round(cp,6),
                        "unrealized_pnl": round(upnl,2),
                        "pnl_pct":        round(pct,2),
                        "leverage":       p.get("leverage", settings["leverage"]),
                    }
            except:
                pass
            pnl = usdt - INITIAL_BALANCE
            return {"usdt":round(usdt,2),"total":round(usdt,2),"pnl":round(pnl,2),
                    "pnl_pct":round((pnl/INITIAL_BALANCE)*100,2),"holdings":holdings}
        except Exception as e:
            if "-2008" not in str(e) and "Invalid Api" not in str(e):
                log_error(f"Futures balance: {e}", notify=False)
            return {"usdt":0,"total":INITIAL_BALANCE,"pnl":0,"pnl_pct":0,"holdings":{}}

    @staticmethod
    def fix_pair(p: str) -> str:
        p = p.upper().strip().replace("USDTUSDT","USDT").replace(".P","")
        if "/" in p: return p
        if p.endswith("USDT"): return f"{p[:-4]}/USDT"
        return f"{p}/USDT"

    def execute(self, pair: str, direction: str, reason: str = "") -> dict:
        direction = direction.lower().strip()
        pair      = self.fix_pair(pair)
        price = amt = total_val = trade_pnl = 0.0
        try:
            self.ex.load_markets()
            price = float(self.ex.fetch_ticker(pair)["last"])
            try:
                self.ex.set_leverage(settings["leverage"], pair)
            except:
                pass
            val = settings["futures_value"]
            amt = float(self.ex.amount_to_precision(pair, val / price))
            total_val = round(amt * price, 2)
            if direction == "buy": direction = "long_open"
            elif direction == "sell":
                direction = "long_close" if (pair in self.positions and self.positions[pair]["side"] == "long") else "short_open"
            if direction == "long_open":
                self.ex.create_market_buy_order(pair, amt, {"reduceOnly": False})
                self.positions[pair] = {"side":"long","entry":price,"amt":amt}
                self.open_times[pair] = datetime.now()
                record_trade_pair(pair, "long_open", "FUTURES", price, amt, total_val, 0, "")
                add_toast(f"🔵 LONG {pair} @ {price:,.4f}", "info")
                if settings.get("telegram_on_trade"):
                    asyncio.create_task(send_telegram(f"🔵 <b>Long — {pair}</b>\n{amt} @ <code>{price:,.4f}</code> ×{settings['leverage']}x"))
            elif direction == "long_close":
                pos = self.positions.get(pair, {})
                amt = pos.get("amt", amt)
                self.ex.create_market_sell_order(pair, amt, {"reduceOnly": True})
                entry     = pos.get("entry", price)
                trade_pnl = round((price - entry) * amt * settings["leverage"], 2)
                pnl_pct   = round(((price-entry)/entry*100)*settings["leverage"],2) if entry else 0
                if pair in self.positions:  del self.positions[pair]
                if pair in self.open_times: del self.open_times[pair]
                update_daily_loss(trade_pnl)
                record_trade_pair(pair, "long_close", "FUTURES", price, amt, total_val, trade_pnl, reason)
                sign = "+" if trade_pnl >= 0 else ""
                em   = "🟢" if trade_pnl >= 0 else "🔴"
                add_toast(f"{em} Long Close {pair}: {sign}{trade_pnl}$", "success" if trade_pnl >= 0 else "error")
                if settings.get("telegram_on_trade"):
                    asyncio.create_task(send_telegram(f"{em} <b>Long Close — {pair}</b>\nPnL: <code>{sign}{trade_pnl}$ ({pnl_pct:+.2f}%)</code>"))
                equity_curve.append({"ts": int(datetime.now().timestamp()*1000), "delta": trade_pnl})
            elif direction == "short_open":
                self.ex.create_market_sell_order(pair, amt, {"reduceOnly": False})
                self.positions[pair] = {"side":"short","entry":price,"amt":amt}
                self.open_times[pair] = datetime.now()
                record_trade_pair(pair, "short_open", "FUTURES", price, amt, total_val, 0, "")
                add_toast(f"🟣 SHORT {pair} @ {price:,.4f}", "info")
                if settings.get("telegram_on_trade"):
                    asyncio.create_task(send_telegram(f"🟣 <b>Short — {pair}</b>\n{amt} @ <code>{price:,.4f}</code> ×{settings['leverage']}x"))
            elif direction == "short_close":
                pos = self.positions.get(pair, {})
                amt = pos.get("amt", amt)
                self.ex.create_market_buy_order(pair, amt, {"reduceOnly": True})
                entry     = pos.get("entry", price)
                trade_pnl = round((entry - price) * amt * settings["leverage"], 2)
                pnl_pct   = round(((entry-price)/entry*100)*settings["leverage"],2) if entry else 0
                if pair in self.positions:  del self.positions[pair]
                if pair in self.open_times: del self.open_times[pair]
                update_daily_loss(trade_pnl)
                record_trade_pair(pair, "short_close", "FUTURES", price, amt, total_val, trade_pnl, reason)
                sign = "+" if trade_pnl >= 0 else ""
                em   = "🟢" if trade_pnl >= 0 else "🔴"
                add_toast(f"{em} Short Close {pair}: {sign}{trade_pnl}$", "success" if trade_pnl >= 0 else "error")
                if settings.get("telegram_on_trade"):
                    asyncio.create_task(send_telegram(f"{em} <b>Short Close — {pair}</b>\nPnL: <code>{sign}{trade_pnl}$ ({pnl_pct:+.2f}%)</code>"))
                equity_curve.append({"ts": int(datetime.now().timestamp()*1000), "delta": trade_pnl})
            else:
                raise Exception(f"Unknown direction: {direction}")
            record = _make_record(pair, direction, "FUTURES", price, amt, total_val, trade_pnl, reason, True)
            self.trades.appendleft(record)
            return record
        except Exception as e:
            log_error(f"[FUTURES] {direction} {pair}: {e}")
            record = _make_record(pair, direction, "FUTURES", price, amt, total_val, 0, reason, False, str(e)[:100])
            self.trades.appendleft(record)
            return record

    def close_all(self):
        for pair, pos in list(self.positions.items()):
            try:
                if pos["side"] == "long":
                    self.ex.create_market_sell_order(pair, pos["amt"], {"reduceOnly": True})
                else:
                    self.ex.create_market_buy_order(pair, pos["amt"], {"reduceOnly": True})
                del self.positions[pair]
            except Exception as e:
                log_error(f"Close {pair}: {e}", notify=False)


# ══════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════
def _reason_en(r: str) -> str:
    return {"stop_loss":"Stop Loss 🛑","peak_exit":"Peak Exit 🎯","trailing_stop":"Trailing Stop 📉"}.get(r,"Exit")

def _make_record(pair,act,market,price,amt,total,pnl,reason,success,err="") -> dict:
    return {
        "id":      int(datetime.now().timestamp()*1000),
        "time":    datetime.now().strftime("%H:%M:%S"),
        "date":    datetime.now().strftime("%d/%m/%Y"),
        "market":  market,
        "pair":    pair,
        "act":     act,
        "price":   round(price,6),
        "amount":  round(amt,6),
        "total":   round(total,2),
        "pnl":     round(pnl,2),
        "reason":  reason,
        "success": success,
        "err":     err,
    }

spot_bot    = SpotBot()
futures_bot = FuturesBot()


def record_trade_pair(pair: str, act: str, market: str, price: float,
                       amt: float, total: float, pnl: float, reason: str,
                       buy_price: float = 0.0, buy_time: str = "", buy_date: str = ""):
    """
    يربط عمليات الشراء والبيع معاً في سجل واحد.
    - عند الشراء  → يحفظ في open_trades انتظاراً للبيع
    - عند البيع   → يكمل السجل ويحركه إلى trade_pairs
    - العملات المفتوحة تظهر أيضاً في الجدول بحالة OPEN
    """
    now_time = datetime.now().strftime("%H:%M:%S")
    now_date = datetime.now().strftime("%d/%m/%Y")
    key = f"{market}:{pair}"

    is_open  = act in ("buy", "long_open", "short_open")
    is_close = act in ("sell", "long_close", "short_close")

    if is_open:
        open_trades[key] = {
            "id":         int(datetime.now().timestamp() * 1000),
            "pair":       pair,
            "market":     market,
            "side":       act,
            "buy_price":  price,
            "buy_amount": amt,
            "buy_total":  total,
            "buy_time":   now_time,
            "buy_date":   now_date,
            "status":     "OPEN",
        }

    elif is_close and key in open_trades:
        op = open_trades.pop(key)
        bp   = op["buy_price"]
        dur_sec = 0
        try:
            bt  = datetime.strptime(f"{op['buy_date']} {op['buy_time']}", "%d/%m/%Y %H:%M:%S")
            dur_sec = int((datetime.now() - bt).total_seconds())
        except:
            pass
        hrs  = dur_sec // 3600
        mins = (dur_sec % 3600) // 60
        dur_str = f"{hrs}h {mins}m" if hrs else f"{mins}m"

        pnl_pct = round(((price - bp) / bp * 100), 2) if bp > 0 else 0.0
        if act == "short_close":
            pnl_pct = round(((bp - price) / bp * 100), 2) if bp > 0 else 0.0

        trade_pairs.appendleft({
            "id":         op["id"],
            "pair":       pair,
            "market":     market,
            "side":       op["side"],
            "buy_price":  round(bp, 6),
            "buy_amount": round(op["buy_amount"], 6),
            "buy_total":  round(op["buy_total"], 2),
            "buy_time":   op["buy_time"],
            "buy_date":   op["buy_date"],
            "sell_price": round(price, 6),
            "sell_total": round(total, 2),
            "sell_time":  now_time,
            "sell_date":  now_date,
            "pnl":        round(pnl, 2),
            "pnl_pct":    pnl_pct,
            "reason":     reason,
            "duration":   dur_str,
            "status":     "CLOSED",
        })

    elif is_close and key not in open_trades:
        # بيع بدون شراء مسجل (نادر) — نسجله ببيانات جزئية
        trade_pairs.appendleft({
            "id":         int(datetime.now().timestamp() * 1000),
            "pair":       pair,
            "market":     market,
            "side":       act,
            "buy_price":  buy_price,
            "buy_amount": amt,
            "buy_total":  0,
            "buy_time":   buy_time or "—",
            "buy_date":   buy_date or "—",
            "sell_price": round(price, 6),
            "sell_total": round(total, 2),
            "sell_time":  now_time,
            "sell_date":  now_date,
            "pnl":        round(pnl, 2),
            "pnl_pct":    round(((price - buy_price) / buy_price * 100), 2) if buy_price > 0 else 0,
            "reason":     reason,
            "duration":   "—",
            "status":     "CLOSED",
        })


def get_all_trade_pairs() -> list:
    """يُعيد كل الصفقات: المغلقة + المفتوحة حالياً (live unrealized)"""
    closed = list(trade_pairs)
    # أضف المفتوحة من open_trades
    live = []
    for key, op in open_trades.items():
        # نحسب PnL الحالي إذا أمكن
        try:
            pair   = op["pair"]
            mkt    = op["market"]
            ticker = spot_bot.ex.fetch_ticker(pair) if mkt == "SPOT" else futures_bot.ex.fetch_ticker(pair)
            cur    = float(ticker["last"])
            bp     = op["buy_price"]
            amt    = op["buy_amount"]
            upnl   = round((cur - bp) * amt, 2)
            upct   = round(((cur - bp) / bp * 100), 2) if bp > 0 else 0.0
        except:
            cur  = op["buy_price"]
            upnl = 0.0
            upct = 0.0
        try:
            bt      = datetime.strptime(f"{op['buy_date']} {op['buy_time']}", "%d/%m/%Y %H:%M:%S")
            dur_sec = int((datetime.now() - bt).total_seconds())
            hrs  = dur_sec // 3600
            mins = (dur_sec % 3600) // 60
            dur_str = f"{hrs}h {mins}m" if hrs else f"{mins}m"
        except:
            dur_str = "—"

        live.append({
            "id":           op["id"],
            "pair":         op["pair"],
            "market":       op["market"],
            "side":         op["side"],
            "buy_price":    round(op["buy_price"], 6),
            "buy_amount":   round(op["buy_amount"], 6),
            "buy_total":    round(op["buy_total"], 2),
            "buy_time":     op["buy_time"],
            "buy_date":     op["buy_date"],
            "sell_price":   round(cur, 6),   # السعر الحالي
            "sell_total":   0,
            "sell_time":    "—",
            "sell_date":    "—",
            "pnl":          upnl,
            "pnl_pct":      upct,
            "reason":       "—",
            "duration":     dur_str,
            "status":       "OPEN",
        })

    return live + closed   # المفتوحة أولاً


# ══════════════════════════════════════════
# Top Movers

# ══════════════════════════════════════════
async def get_top_movers(limit: int = 10) -> list:
    try:
        tickers = spot_bot.ex.fetch_tickers()
        movers  = []
        for sym, t in tickers.items():
            if not sym.endswith("/USDT"):
                continue
            pct = float(t.get("percentage",0) or 0)
            vol = float(t.get("quoteVolume",0) or 0)
            if vol < 500_000:
                continue
            movers.append({
                "symbol":     sym.replace("/USDT",""),
                "price":      t.get("last",0),
                "change_pct": round(pct,2),
                "volume_m":   round(vol/1_000_000,2),
                "high":       t.get("high",0),
                "low":        t.get("low",0),
            })
        movers.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
        return movers[:limit]
    except Exception as e:
        log_error(f"Movers: {e}", notify=False)
        return []


# ══════════════════════════════════════════
# Full State
# ══════════════════════════════════════════
async def get_full_state() -> dict:
    spot_bal    = await spot_bot.get_balance()
    futures_bal = await futures_bot.get_balance()
    all_trades  = sorted(
        list(spot_bot.trades) + list(futures_bot.trades),
        key=lambda x: x.get("id",0), reverse=True
    )[:1000]
    stats        = calc_advanced_stats(all_trades)
    period_stats = get_period_stats(all_trades, settings.get("report_hours",24))
    # Build equity curve (running balance)
    running = INITIAL_BALANCE
    eq = []
    for snap in reversed(list(equity_curve)):
        running += snap["delta"]
        eq.append({"ts": snap["ts"], "value": round(running, 2)})
    return {
        "spot":         spot_bal,
        "futures":      futures_bal,
        "trades":       all_trades,
        "settings":     {k:v for k,v in settings.items() if k not in ("daily_loss_current","daily_loss_date")},
        "stats":        stats,
        "period_stats": period_stats,
        "errors":       list(error_logs)[:100],
        "login_logs":   list(login_logs)[:50],
        "daily_loss":   {"current": round(settings["daily_loss_current"],2), "limit": round(INITIAL_BALANCE*settings["daily_loss_limit_pct"]/100,2)},
        "equity_curve":   eq[-200:],
        "trade_pairs":    get_all_trade_pairs(),
        "toasts":       list(toast_queue),
        "initial_balance": INITIAL_BALANCE,
    }

async def broadcast(data: dict):
    dead = []
    for ws in active_connections:
        try:
            await ws.send_json(data)
        except:
            dead.append(ws)
    for ws in dead:
        if ws in active_connections:
            active_connections.remove(ws)


# ══════════════════════════════════════════
# Models
# ══════════════════════════════════════════
class Signal(BaseModel):
    pair:      str
    direction: str
    reason:    Optional[str] = None
    market:    Optional[str] = None
    model_config = {"extra":"ignore"}

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
async def auth_login(req: AuthReq, request: Request):
    ok  = req.password == DASHBOARD_PASSWORD
    ip  = request.client.host if request.client else "unknown"
    ua  = request.headers.get("user-agent","")[:80]
    login_logs.appendleft({
        "time":    datetime.now().strftime("%H:%M:%S"),
        "date":    datetime.now().strftime("%d/%m/%Y"),
        "ip":      ip,
        "status":  "✅ Success" if ok else "❌ Failed",
        "ua":      ua,
    })
    if not ok:
        log_error(f"Failed login from {ip}", notify=False)
    return {"ok": ok}

@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    active_connections.append(ws)
    try:
        await ws.send_json(await get_full_state())
        while True:
            await asyncio.sleep(5)
            await ws.send_json(await get_full_state())
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if ws in active_connections:
            active_connections.remove(ws)

@app.post("/webhook")
async def webhook(request: Request):
    raw     = await request.body()
    raw_str = raw.decode("utf-8").strip()
    print(f"📨 Webhook: {raw_str[:200]}")
    pair = direction = reason = market = ""
    try:
        data      = json.loads(raw_str)
        pair      = str(data.get("pair","")).upper().strip()
        direction = str(data.get("direction","")).lower().strip()
        reason    = str(data.get("reason",""))
        market    = str(data.get("market","spot")).lower()
    except:
        parts     = [p.strip() for p in raw_str.replace(",","|").split("|")]
        if len(parts) >= 2:
            pair      = parts[0].upper()
            direction = parts[1].lower()
            market    = parts[2].lower() if len(parts) > 2 else "spot"
            reason    = parts[3] if len(parts) > 3 else ""
        else:
            return JSONResponse({"status":"error","msg":"invalid format","raw":raw_str},status_code=422)
    for prefix in ("BINANCE:","BYBIT:","OKX:"):
        pair = pair.replace(prefix,"")
    pair = pair.replace(".P","").replace("-PERP","").replace("_PERP","")
    if ":" in pair: pair = pair.split(":")[1]
    if not pair or not direction:
        return JSONResponse({"status":"error","msg":"missing pair or direction"},status_code=422)
    s = Signal(pair=pair, direction=direction, reason=reason, market=market)
    if settings.get("emergency_stop"):  return {"status":"emergency_stop","ok":False}
    if not settings.get("active"):      return {"status":"inactive","ok":False}
    ok_sess, sess_msg = is_session_active()
    if not ok_sess: return {"status":"outside_session","message":sess_msg,"ok":False}
    ok_cal, cal_msg = is_calendar_paused()
    if ok_cal: return {"status":"calendar_paused","event":cal_msg,"ok":False}
    if direction in ("long_open","long_close","short_open","short_close"): market = "futures"
    if market == "futures" and not settings.get("futures_enabled"):
        return {"status":"futures_disabled","ok":False}
    async def execute_bg():
        result = futures_bot.execute(s.pair,direction,reason) if market=="futures" else spot_bot.execute(s.pair,direction,reason)
        await broadcast(await get_full_state())
        print(f"✅ Executed: {result}")
    asyncio.create_task(execute_bg())
    return {"status":"received","ok":True}

@app.post("/settings/update")
async def update_setting(req: SettingReq):
    if req.key in settings:
        settings[req.key] = req.value
    await broadcast(await get_full_state())
    return {"ok":True}

@app.post("/control/toggle")
async def ctrl_toggle():
    if not settings.get("emergency_stop"):
        settings["active"] = not settings["active"]
        add_toast("✅ Bot activated" if settings["active"] else "⏸ Bot paused","info")
    await broadcast(await get_full_state())
    return {"active":settings["active"]}

@app.post("/control/emergency")
async def ctrl_emergency():
    settings["emergency_stop"] = True
    settings["active"]         = False
    spot_bot.liquidate_all()
    futures_bot.close_all()
    add_toast("🚨 EMERGENCY STOP — All positions closed!","error")
    await send_telegram("🚨 <b>Emergency Stop</b>\nAll positions liquidated.")
    await broadcast(await get_full_state())
    return {"ok":True}

@app.post("/control/resume")
async def ctrl_resume():
    settings["emergency_stop"] = False
    settings["active"]         = True
    add_toast("▶️ Bot resumed","success")
    await send_telegram("▶️ <b>Trading Resumed</b>")
    await broadcast(await get_full_state())
    return {"ok":True}

@app.post("/liquidate")
async def liquidate():
    spot_bot.liquidate_all()
    await broadcast(await get_full_state())
    return {"ok":True}

@app.post("/liquidate/futures")
async def liquidate_futures():
    futures_bot.close_all()
    await broadcast(await get_full_state())
    return {"ok":True}

@app.post("/errors/clear")
async def clear_errors():
    error_logs.clear()
    await broadcast(await get_full_state())
    return {"ok":True}

@app.get("/movers")
async def movers():
    return await get_top_movers()

@app.get("/health")
async def health():
    return {"status":"ok","version":"8.0.0","active":settings["active"],"emergency":settings["emergency_stop"],"connections":len(active_connections)}


# ══════════════════════════════════════════
# Background
# ══════════════════════════════════════════
@app.on_event("startup")
async def on_startup():
    asyncio.create_task(background_loop())

async def background_loop():
    last_report_date = ""
    while True:
        try:
            await asyncio.sleep(60)
            if settings.get("calendar_enabled"):
                await fetch_economic_calendar()
            if settings.get("telegram_daily_report") and settings.get("telegram_enabled"):
                now_str   = datetime.now().strftime("%H:%M")
                today_str = datetime.now().strftime("%Y-%m-%d")
                if now_str == settings.get("telegram_report_time","00:00") and last_report_date != today_str:
                    last_report_date = today_str
                    all_t = list(spot_bot.trades) + list(futures_bot.trades)
                    st    = calc_advanced_stats(all_t)
                    bal   = await spot_bot.get_balance()
                    sign  = "+" if st["total_pnl"] >= 0 else ""
                    await send_telegram(
                        f"📊 <b>Daily Report — {datetime.now().strftime('%d/%m/%Y')}</b>\n"
                        f"━━━━━━━━━━━━━━━━━\n"
                        f"Trades: {st['total']} | ✅ {st['wins']} | ❌ {st['losses']}\n"
                        f"Win Rate: {st['win_rate']}%\n"
                        f"Profit Factor: {st['profit_factor']}\n"
                        f"Sharpe: {st['sharpe']}\n"
                        f"PnL: {sign}{st['total_pnl']:.2f}$\n"
                        f"Max DD: -{st['max_drawdown']:.2f}$\n"
                        f"Portfolio: {bal['total']:,.2f}$\n"
                        f"━━━━━━━━━━━━━━━━━"
                    )
        except Exception as e:
            print(f"⚠️ Background: {e}")


# ══════════════════════════════════════════
# HTML — SOVEREIGN V8.0
# Binance-style Dark UI | English
# ══════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>SOVEREIGN V8 · Trading Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<style>
/* ═══════════════════════════════════════════
   SOVEREIGN V8 — Binance Dark Theme
   ═══════════════════════════════════════════ */
:root {
  /* Binance Palette */
  --bg0:     #0b0e11;
  --bg1:     #12161c;
  --bg2:     #1e2329;
  --bg3:     #2b3139;
  --border:  rgba(255,255,255,.07);
  --border2: rgba(255,255,255,.04);

  /* Accent */
  --gold:    #f0b90b;
  --gold2:   #f8d12f;
  --gold-bg: rgba(240,185,11,.08);
  --gold-br: rgba(240,185,11,.18);

  /* Status */
  --green:   #0ecb81;
  --green-bg:rgba(14,203,129,.08);
  --green-br:rgba(14,203,129,.18);
  --red:     #f6465d;
  --red-bg:  rgba(246,70,93,.08);
  --red-br:  rgba(246,70,93,.18);
  --blue:    #1890ff;
  --blue-bg: rgba(24,144,255,.08);
  --blue-br: rgba(24,144,255,.18);
  --purple:  #7b61ff;
  --purp-bg: rgba(123,97,255,.08);
  --purp-br: rgba(123,97,255,.18);
  --orange:  #f37b24;
  --oran-bg: rgba(243,123,36,.08);
  --oran-br: rgba(243,123,36,.18);

  /* Text */
  --t1:  #eaecef;
  --t2:  #848e9c;
  --t3:  #474d57;
  --t4:  #2b3139;

  --mono: 'IBM Plex Mono', monospace;
  --sans: 'Inter', sans-serif;
  --r:   8px;
  --r2:  5px;
  --r3:  12px;
}

*      { margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent }
html   { scroll-behavior:smooth }
body   { background:var(--bg0); color:var(--t1); font-family:var(--sans); min-height:100vh; overflow-x:hidden; font-size:14px }
a      { color:inherit; text-decoration:none }
button { cursor:pointer; border:none; background:none; font-family:inherit }
input, select { font-family:inherit; color:var(--t1) }

/* ─── Scrollbar ─── */
::-webkit-scrollbar { width:4px; height:4px }
::-webkit-scrollbar-track { background:var(--bg0) }
::-webkit-scrollbar-thumb { background:var(--bg3); border-radius:2px }

/* ═══════════════ LOGIN ═══════════════ */
#loginPage {
  position:fixed; inset:0; background:var(--bg0);
  z-index:1000; display:flex; align-items:center; justify-content:center;
}
.login-box {
  background:var(--bg1); border:1px solid var(--gold-br);
  border-radius:16px; padding:48px 40px; width:380px; text-align:center;
  position:relative;
  box-shadow: 0 0 60px rgba(240,185,11,.06);
}
.login-logo {
  font-family:var(--mono); font-size:22px; font-weight:700;
  color:var(--gold); letter-spacing:4px; margin-bottom:4px;
}
.login-sub {
  font-family:var(--mono); font-size:9px; color:var(--t3);
  letter-spacing:3px; margin-bottom:36px;
}
.login-input {
  width:100%; background:var(--bg2); border:1px solid var(--border);
  border-radius:var(--r); color:var(--t1); font-family:var(--mono);
  font-size:16px; padding:14px; text-align:center; letter-spacing:8px;
  outline:none; transition:border-color .2s; margin-bottom:12px;
}
.login-input:focus { border-color:var(--gold-br) }
.login-btn {
  width:100%; background:var(--gold); color:#000;
  font-family:var(--mono); font-size:12px; font-weight:700;
  padding:14px; border-radius:var(--r); letter-spacing:2px;
  transition:all .2s;
}
.login-btn:hover { background:var(--gold2); transform:translateY(-1px) }
.login-err { color:var(--red); font-size:11px; margin-top:10px; display:none; font-family:var(--mono) }

/* ═══════════════ LAYOUT ═══════════════ */
#app { display:none }
.topbar {
  background:var(--bg1); border-bottom:1px solid var(--border);
  height:56px; display:flex; align-items:center; padding:0 20px;
  gap:16px; position:sticky; top:0; z-index:100;
}
.logo { font-family:var(--mono); font-size:16px; font-weight:700; color:var(--gold); letter-spacing:3px }
.logo span { font-size:9px; font-weight:400; color:var(--t3); letter-spacing:1px; display:block; margin-top:1px }
.topbar-mid { flex:1; display:flex; align-items:center; gap:20px }
.topbar-stat { display:flex; flex-direction:column; align-items:center }
.topbar-stat .lbl { font-size:9px; color:var(--t3); font-family:var(--mono); text-transform:uppercase; letter-spacing:.8px }
.topbar-stat .val { font-family:var(--mono); font-size:12px; font-weight:600; margin-top:2px }
.topbar-right { display:flex; align-items:center; gap:8px }
.conn-dot { width:7px; height:7px; border-radius:50%; background:var(--t3); animation:blink 2s infinite }
.conn-dot.live { background:var(--green) }
.conn-txt { font-family:var(--mono); font-size:10px; color:var(--t2) }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }

.wrap { max-width:1480px; margin:0 auto; padding:16px }

/* ─── Tabs ─── */
.tabs { display:flex; gap:1px; background:var(--bg2); border-radius:var(--r); padding:4px; margin-bottom:16px }
.tab {
  flex:1; padding:9px 8px; border-radius:var(--r2);
  font-size:12px; font-weight:500; color:var(--t2);
  transition:all .18s; white-space:nowrap; text-align:center;
}
.tab:hover:not(.active) { color:var(--t1); background:var(--bg3) }
.tab.active { background:var(--bg3); color:var(--gold); font-weight:600 }

.panel { display:none }
.panel.active { display:block }

/* ═══════════════ CARDS ═══════════════ */
.card {
  background:var(--bg1); border:1px solid var(--border);
  border-radius:var(--r3); overflow:hidden;
}
.card-head {
  padding:14px 18px; border-bottom:1px solid var(--border2);
  display:flex; align-items:center; justify-content:space-between;
}
.card-title { font-size:11px; color:var(--t2); font-family:var(--mono); text-transform:uppercase; letter-spacing:1.5px }
.card-badge {
  font-family:var(--mono); font-size:10px; padding:2px 10px;
  border-radius:20px; font-weight:600;
}
.badge-gold { background:var(--gold-bg); color:var(--gold); border:1px solid var(--gold-br) }
.badge-green { background:var(--green-bg); color:var(--green); border:1px solid var(--green-br) }
.badge-red { background:var(--red-bg); color:var(--red); border:1px solid var(--red-br) }
.badge-blue { background:var(--blue-bg); color:var(--blue); border:1px solid var(--blue-br) }
.badge-purp { background:var(--purp-bg); color:var(--purple); border:1px solid var(--purp-br) }

/* ═══════════════ GRID LAYOUTS ═══════════════ */
.g2 { display:grid; grid-template-columns:1fr 1fr; gap:12px }
.g3 { display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px }
.g4 { display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:12px }
.g5 { display:grid; grid-template-columns:repeat(5,1fr); gap:10px }
.g6 { display:grid; grid-template-columns:repeat(6,1fr); gap:10px }
@media(max-width:1100px) { .g6{grid-template-columns:repeat(3,1fr)} .g5{grid-template-columns:repeat(3,1fr)} }
@media(max-width:800px)  { .g4,.g3{grid-template-columns:1fr 1fr} .g2{grid-template-columns:1fr} }
@media(max-width:500px)  { .g4{grid-template-columns:1fr 1fr} }

/* ═══════════════ METRIC CARDS ═══════════════ */
.metric-card {
  background:var(--bg1); border:1px solid var(--border);
  border-radius:var(--r3); padding:18px 20px;
  position:relative; overflow:hidden; transition:border-color .2s;
}
.metric-card:hover { border-color:var(--gold-br) }
.metric-card .mc-icon { position:absolute; right:14px; top:12px; font-size:20px; opacity:.12 }
.metric-card .mc-lbl { font-size:10px; color:var(--t2); font-family:var(--mono); text-transform:uppercase; letter-spacing:1px; margin-bottom:8px }
.metric-card .mc-val { font-family:var(--mono); font-size:22px; font-weight:700; line-height:1; margin-bottom:5px }
.metric-card .mc-sub { font-size:10px; color:var(--t2); font-family:var(--mono) }
.mc-gold  { color:var(--gold) }
.mc-green { color:var(--green) }
.mc-red   { color:var(--red) }
.mc-blue  { color:var(--blue) }
.mc-purp  { color:var(--purple) }
.mc-muted { color:var(--t2) }

/* ═══════════════ BALANCE PANEL ═══════════════ */
.bal-panel {
  background:var(--bg1); border:1px solid var(--border);
  border-radius:var(--r3); padding:20px;
}
.bal-panel.spot-panel { border-top:2px solid var(--blue) }
.bal-panel.fut-panel  { border-top:2px solid var(--purple) }
.bp-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:18px }
.bp-title { font-family:var(--mono); font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase }
.bp-title.spot { color:var(--blue) }
.bp-title.fut  { color:var(--purple) }
.bp-tag { font-family:var(--mono); font-size:9px; padding:3px 8px; border-radius:4px; font-weight:700 }
.bp-metrics { display:grid; grid-template-columns:repeat(3,1fr); gap:12px }
.bpm .lbl { font-size:9px; color:var(--t2); font-family:var(--mono); text-transform:uppercase; letter-spacing:.8px; margin-bottom:5px }
.bpm .val { font-family:var(--mono); font-size:20px; font-weight:700 }
.bpm .sub { font-size:9px; color:var(--t3); margin-top:3px; font-family:var(--mono) }

/* ─── Daily Loss Bar ─── */
.dl-bar-wrap { margin-top:16px }
.dl-bar-row { display:flex; justify-content:space-between; font-size:10px; color:var(--t2); font-family:var(--mono); margin-bottom:5px }
.dl-bar { height:3px; background:var(--bg3); border-radius:2px; overflow:hidden }
.dl-fill { height:100%; border-radius:2px; transition:width .6s, background .4s }

/* ─── Futures Positions ─── */
.pos-row {
  display:flex; align-items:center; gap:10px; padding:10px 14px;
  border-bottom:1px solid var(--border2); font-family:var(--mono); font-size:11px;
}
.pos-sym { font-weight:700; color:var(--t1); min-width:90px }
.pos-side { padding:2px 7px; border-radius:4px; font-size:9px; font-weight:700; text-transform:uppercase }
.pos-long  { background:var(--blue-bg); color:var(--blue); border:1px solid var(--blue-br) }
.pos-short { background:var(--purp-bg); color:var(--purple); border:1px solid var(--purp-br) }

/* ═══════════════ BUTTONS ═══════════════ */
.btn {
  display:inline-flex; align-items:center; gap:5px; padding:8px 14px;
  border-radius:var(--r2); font-size:12px; font-weight:600;
  transition:all .15s; white-space:nowrap; cursor:pointer; border:1px solid transparent;
}
.btn:active { transform:scale(.97) }
.btn-gold   { background:var(--gold); color:#000; border-color:var(--gold) }
.btn-gold:hover { background:var(--gold2) }
.btn-green  { background:var(--green-bg); color:var(--green); border-color:var(--green-br) }
.btn-green:hover { background:rgba(14,203,129,.14) }
.btn-red    { background:var(--red-bg); color:var(--red); border-color:var(--red-br) }
.btn-red:hover { background:rgba(246,70,93,.14) }
.btn-blue   { background:var(--blue-bg); color:var(--blue); border-color:var(--blue-br) }
.btn-blue:hover { background:rgba(24,144,255,.14) }
.btn-ghost  { background:var(--bg2); color:var(--t2); border-color:var(--border) }
.btn-ghost:hover { color:var(--t1); background:var(--bg3) }
.btn-yellow { background:rgba(240,185,11,.1); color:var(--gold); border-color:var(--gold-br) }
.btn-yellow:hover { background:rgba(240,185,11,.18) }

/* ─── Action Bar ─── */
.abar { display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-bottom:14px }
.adiv { width:1px; height:22px; background:var(--border); align-self:center }

/* ═══════════════ TABLE ═══════════════ */
.tbl-wrap { overflow-x:auto }
table { width:100%; border-collapse:collapse }
thead th {
  padding:10px 14px; font-size:9px; font-family:var(--mono);
  color:var(--t2); text-transform:uppercase; letter-spacing:1.2px;
  text-align:left; background:var(--bg2); border-bottom:1px solid var(--border);
  white-space:nowrap;
}
tbody tr { border-bottom:1px solid var(--border2); transition:background .12s }
tbody tr:hover { background:var(--bg2) }
tbody tr.flash-row { animation:flash-anim 2s ease-out }
@keyframes flash-anim { 0%{background:rgba(240,185,11,.1)} 100%{background:transparent} }
td { padding:11px 14px; font-size:12px; white-space:nowrap; text-align:left }
.td-mono  { font-family:var(--mono) }
.td-muted { color:var(--t2); font-size:10px; font-family:var(--mono) }
.td-pair  { font-family:var(--mono); font-weight:700 }
.td-price { font-family:var(--mono); color:var(--gold) }

/* Trade type badges */
.tb { display:inline-flex; align-items:center; padding:2px 8px; border-radius:4px; font-family:var(--mono); font-size:9px; font-weight:700; letter-spacing:.5px; text-transform:uppercase; white-space:nowrap }
.tb-buy     { background:var(--green-bg); color:var(--green); border:1px solid var(--green-br) }
.tb-sell    { background:var(--red-bg); color:var(--red); border:1px solid var(--red-br) }
.tb-long    { background:var(--blue-bg); color:var(--blue); border:1px solid var(--blue-br) }
.tb-lclose  { background:rgba(24,144,255,.04); color:var(--blue); border:1px solid rgba(24,144,255,.12) }
.tb-short   { background:var(--purp-bg); color:var(--purple); border:1px solid var(--purp-br) }
.tb-sclose  { background:rgba(123,97,255,.04); color:var(--purple); border:1px solid rgba(123,97,255,.12) }
.mkt-s { background:var(--blue-bg); color:var(--blue); font-size:8px; padding:1px 5px; border-radius:3px; font-family:var(--mono); font-weight:700 }
.mkt-f { background:var(--purp-bg); color:var(--purple); font-size:8px; padding:1px 5px; border-radius:3px; font-family:var(--mono); font-weight:700 }
.reason-tag { font-size:10px; color:var(--t2); font-family:var(--mono) }

/* PnL */
.pnl-pos { color:var(--green); font-family:var(--mono); font-weight:600 }
.pnl-neg { color:var(--red);   font-family:var(--mono); font-weight:600 }
.pnl-nil { color:var(--t3);    font-family:var(--mono) }

/* Empty state */
.empty-state { padding:48px; text-align:center; color:var(--t3) }
.empty-state .ei { font-size:28px; display:block; margin-bottom:10px; opacity:.3 }
.empty-state .et { font-family:var(--mono); font-size:11px }

/* ═══════════════ SETTINGS ═══════════════ */
.settings-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:12px }
.s-group { background:var(--bg2); border:1px solid var(--border); border-radius:var(--r3); padding:18px }
.s-group-title { font-size:10px; color:var(--t2); font-family:var(--mono); text-transform:uppercase; letter-spacing:1.5px; margin-bottom:16px; display:flex; align-items:center; gap:6px }
.s-row { display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:12px }
.s-row:last-child { margin-bottom:0 }
.s-lbl { font-size:12px; color:var(--t1) }
.s-sub { font-size:10px; color:var(--t2); margin-top:2px }

/* Toggle */
.toggle { position:relative; display:inline-block; width:40px; height:22px; flex-shrink:0 }
.toggle input { opacity:0; width:0; height:0 }
.tgl-slider { position:absolute; cursor:pointer; inset:0; background:var(--bg3); border-radius:22px; transition:.25s; border:1px solid var(--border) }
.tgl-slider:before { position:absolute; content:""; height:16px; width:16px; left:2px; bottom:2px; background:var(--t3); border-radius:50%; transition:.25s }
.toggle input:checked + .tgl-slider { background:rgba(14,203,129,.15); border-color:var(--green-br) }
.toggle input:checked + .tgl-slider:before { transform:translateX(18px); background:var(--green) }

/* Number input */
.n-input {
  background:var(--bg3); border:1px solid var(--border); color:var(--t1);
  font-family:var(--mono); font-size:12px; font-weight:600;
  width:72px; padding:5px 8px; border-radius:var(--r2); text-align:center; outline:none;
  transition:border-color .15s;
}
.n-input:focus { border-color:var(--gold-br) }
.n-input[type=time] { width:90px }

.sel-input {
  background:var(--bg3); border:1px solid var(--border); color:var(--t1);
  font-size:12px; padding:5px 8px; border-radius:var(--r2); cursor:pointer; outline:none;
}
.sel-input:focus { border-color:var(--gold-br) }

/* ═══════════════ EQUITY CHART ═══════════════ */
.chart-wrap { padding:16px 20px }
#equityCanvas { width:100%; height:200px; display:block }

/* ═══════════════ MOVERS ═══════════════ */
.mover-card {
  background:var(--bg2); border:1px solid var(--border);
  border-radius:var(--r3); padding:16px; text-align:center;
  transition:border-color .18s, transform .18s; cursor:pointer;
}
.mover-card:hover { border-color:var(--gold-br); transform:translateY(-2px) }
.mover-sym  { font-family:var(--mono); font-size:13px; font-weight:700; margin-bottom:6px }
.mover-pct  { font-family:var(--mono); font-size:17px; font-weight:700 }
.mover-info { font-family:var(--mono); font-size:9px; color:var(--t2); margin-top:4px }

/* ═══════════════ TOAST NOTIFICATIONS ═══════════════ */
#toastContainer {
  position:fixed; top:68px; right:16px; z-index:9999;
  display:flex; flex-direction:column; gap:8px; pointer-events:none;
  max-width:340px;
}
.toast {
  padding:12px 16px; border-radius:var(--r); font-size:12px;
  font-family:var(--mono); display:flex; align-items:center; gap:8px;
  animation:slideIn .25s ease-out; pointer-events:all;
  border:1px solid; backdrop-filter:blur(10px);
  box-shadow:0 8px 24px rgba(0,0,0,.4);
}
.toast.success { background:rgba(14,203,129,.12); border-color:var(--green-br); color:var(--green) }
.toast.error   { background:rgba(246,70,93,.12); border-color:var(--red-br); color:var(--red) }
.toast.info    { background:rgba(24,144,255,.12); border-color:var(--blue-br); color:var(--blue) }
.toast.warning { background:rgba(243,123,36,.12); border-color:var(--oran-br); color:var(--orange) }
@keyframes slideIn { from{transform:translateX(120%);opacity:0} to{transform:translateX(0);opacity:1} }
@keyframes slideOut { from{transform:translateX(0);opacity:1} to{transform:translateX(120%);opacity:0} }

/* ═══════════════ MODAL ═══════════════ */
.modal { display:none; position:fixed; inset:0; background:rgba(0,0,0,.75); z-index:500; align-items:center; justify-content:center; padding:20px }
.modal.open { display:flex }
.modal-box {
  background:var(--bg1); border:1px solid var(--gold-br);
  border-radius:16px; padding:28px; max-width:460px; width:100%;
  position:relative; max-height:90vh; overflow-y:auto;
}
.modal-title { font-family:var(--mono); color:var(--gold); font-size:12px; font-weight:700; letter-spacing:2px; margin-bottom:18px }
.modal-close { position:absolute; top:14px; right:16px; color:var(--t2); font-size:18px; cursor:pointer; transition:color .15s }
.modal-close:hover { color:var(--t1) }

/* ═══════════════ ANALYTICS ═══════════════ */
.analytics-row { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:14px }
.stat-row { display:flex; justify-content:space-between; align-items:center; padding:10px 0; border-bottom:1px solid var(--border2) }
.stat-row:last-child { border-bottom:none }
.stat-lbl { font-size:12px; color:var(--t2) }
.stat-val { font-family:var(--mono); font-size:13px; font-weight:600 }

/* ─── Period selector ─── */
.period-tabs { display:flex; gap:4px; background:var(--bg2); padding:4px; border-radius:var(--r2); width:fit-content }
.period-tab { padding:5px 12px; border-radius:3px; font-size:11px; font-family:var(--mono); font-weight:600; color:var(--t2); cursor:pointer; transition:all .15s }
.period-tab.active { background:var(--bg3); color:var(--gold) }

/* ─── Heatmap ─── */
.heatmap-grid { display:grid; grid-template-columns:repeat(24,1fr); gap:2px }
.hmap-cell { aspect-ratio:1; border-radius:2px; position:relative; cursor:default }
.hmap-lbl { font-size:7px; color:var(--t3); font-family:var(--mono); text-align:center; margin-bottom:3px }

/* ═══════════════ STATE INDICATOR ═══════════════ */
.state-badge {
  padding:5px 12px; border-radius:20px;
  font-family:var(--mono); font-size:9px; font-weight:700;
  display:inline-flex; align-items:center; gap:5px; border:1px solid;
}
.state-active   { background:var(--green-bg); color:var(--green); border-color:var(--green-br) }
.state-paused   { background:rgba(240,185,11,.08); color:var(--gold); border-color:var(--gold-br) }
.state-emer     { background:var(--red-bg); color:var(--red); border-color:var(--red-br); animation:blink 1s infinite }
.state-calendar { background:var(--oran-bg); color:var(--orange); border-color:var(--oran-br) }

/* ═══════════════ PORTFOLIO TABLE ═══════════════ */
.port-coin { display:flex; align-items:center; gap:8px }
.coin-dot { width:8px; height:8px; border-radius:50%; background:var(--gold); flex-shrink:0 }
.coin-name { font-family:var(--mono); font-weight:700 }

/* ─── Progress bar (concentration) ─── */
.conc-bar { height:3px; background:var(--bg3); border-radius:2px; margin-top:4px; overflow:hidden }
.conc-fill { height:100%; border-radius:2px }

/* ─── Trade Pairs ─── */
.tp-open-row   { background:rgba(24,144,255,.03) }
.tp-win-row    { background:rgba(14,203,129,.025) }
.tp-loss-row   { background:rgba(246,70,93,.025) }
.tp-status-open   { background:var(--blue-bg); color:var(--blue); border:1px solid var(--blue-br); font-family:var(--mono); font-size:9px; padding:2px 8px; border-radius:4px; font-weight:700 }
.tp-status-closed-win  { background:var(--green-bg); color:var(--green); border:1px solid var(--green-br); font-family:var(--mono); font-size:9px; padding:2px 8px; border-radius:4px; font-weight:700 }
.tp-status-closed-loss { background:var(--red-bg); color:var(--red); border:1px solid var(--red-br); font-family:var(--mono); font-size:9px; padding:2px 8px; border-radius:4px; font-weight:700 }
.tp-live-price { color:var(--blue); font-family:var(--mono); font-size:11px }
.tp-live-price::after { content:" ●"; font-size:7px; animation:blink 1.5s infinite }
.tp-arrow { font-size:10px; color:var(--t3); margin:0 3px }

/* ─── Divider ─── */
.divider { height:1px; background:var(--border); margin:14px 0 }

/* ─── Section spacing ─── */
.mb12 { margin-bottom:12px }
.mb16 { margin-bottom:16px }

/* ─── Footer ─── */
.footer { text-align:center; padding:24px; color:var(--t3); font-family:var(--mono); font-size:9px; letter-spacing:2px }

/* ─── Ticker bar ─── */
.ticker-bar {
  background:var(--bg1); border-bottom:1px solid var(--border2);
  padding:6px 20px; display:flex; align-items:center; gap:14px;
  font-family:var(--mono); font-size:10px; color:var(--t2);
  overflow-x:auto;
}
.ticker-sep { color:var(--t4) }
.ticker-live { color:var(--gold); font-weight:700; background:var(--gold-bg); padding:1px 7px; border-radius:3px }
</style>
</head>
<body>

<!-- ═══ TOAST CONTAINER ═══ -->
<div id="toastContainer"></div>

<!-- ═══ LOGIN ═══ -->
<div id="loginPage">
  <div class="login-box">
    <div class="login-logo">SOVEREIGN</div>
    <div class="login-sub">TRADING SYSTEM · V8.0</div>
    <input id="pwInput" class="login-input" type="password" placeholder="••••••••" autocomplete="current-password" onkeydown="if(event.key==='Enter')doLogin()">
    <button class="login-btn" onclick="doLogin()">ENTER SYSTEM →</button>
    <div class="login-err" id="loginErr">❌ Incorrect password</div>
  </div>
</div>

<!-- ═══ APP ═══ -->
<div id="app">

  <!-- Top Bar -->
  <div class="topbar">
    <div class="logo">SOVEREIGN<span>SPOT + FUTURES · V8.0</span></div>
    <div class="topbar-mid">
      <div class="topbar-stat"><span class="lbl">Portfolio</span><span class="val mc-gold" id="tb-total">--</span></div>
      <div class="topbar-stat"><span class="lbl">Total PnL</span><span class="val" id="tb-pnl">--</span></div>
      <div class="topbar-stat"><span class="lbl">Win Rate</span><span class="val mc-green" id="tb-wr">--</span></div>
      <div class="topbar-stat"><span class="lbl">Open</span><span class="val mc-blue" id="tb-open">0</span></div>
      <span id="stateBadge" class="state-badge state-active">⏳ Loading</span>
    </div>
    <div class="topbar-right">
      <div class="conn-dot" id="connDot"></div>
      <span class="conn-txt" id="connTxt">Connecting...</span>
    </div>
  </div>

  <!-- Ticker Bar -->
  <div class="ticker-bar">
    <span class="ticker-live">⚡ LIVE</span>
    <span id="clock">--:--:--</span>
    <span class="ticker-sep">|</span>
    <span>Loss Today: <span id="dl-ticker" style="color:var(--t1)">--</span></span>
    <span class="ticker-sep">|</span>
    <span>Updated: <span id="last-upd" style="color:var(--t1)">--</span></span>
    <span class="ticker-sep" id="cal-sep" style="display:none">|</span>
    <span id="cal-ticker" style="color:var(--orange);display:none"></span>
  </div>

  <div class="wrap">

    <!-- Tabs -->
    <div class="tabs">
      <button class="tab active" onclick="switchTab('overview',this)">📊 Overview</button>
      <button class="tab" onclick="switchTab('analytics',this)">📈 Analytics</button>
      <button class="tab" onclick="switchTab('portfolio',this)">💼 Portfolio</button>
      <button class="tab" onclick="switchTab('trades',this)">📋 Trades</button>
      <button class="tab" onclick="switchTab('tradepairs',this)">🔗 Trade Pairs</button>
      <button class="tab" onclick="switchTab('settings',this)">⚙️ Settings</button>
      <button class="tab" onclick="switchTab('movers',this);loadMovers()">🔥 Movers</button>
      <button class="tab" onclick="switchTab('security',this)">🔒 Security</button>
      <button class="tab" onclick="switchTab('agents',this);loadAgents()">🤖 AI Agents</button>
    </div>

    <!-- ══════ OVERVIEW ══════ -->
    <div id="tab-overview" class="panel active">
      <!-- Action Bar -->
      <div class="abar">
        <button class="btn btn-yellow" id="toggleBtn" onclick="toggleBot()">⏸ Pause</button>
        <button class="btn btn-red" id="emerBtn" onclick="emergencyStop()">🚨 Emergency Stop</button>
        <button class="btn btn-green" id="resumeBtn" style="display:none" onclick="resumeBot()">▶ Resume</button>
        <div class="adiv"></div>
        <button class="btn btn-red btn-ghost" onclick="liquidateSpot()" style="border-color:var(--red-br);color:var(--red)">⚠ Liquidate Spot</button>
        <button class="btn btn-red btn-ghost" onclick="liquidateFutures()" style="border-color:var(--red-br);color:var(--red)">⚠ Close Futures</button>
        <div class="adiv"></div>
        <button class="btn btn-gold" onclick="openModal('excelModal')">📊 Export Excel</button>
      </div>

      <!-- Balance Grid -->
      <div class="g2 mb16">
        <!-- Spot -->
        <div class="bal-panel spot-panel">
          <div class="bp-header">
            <div class="bp-title spot">💧 SPOT</div>
            <span class="bp-tag badge-blue">Testnet</span>
          </div>
          <div class="bp-metrics">
            <div class="bpm"><div class="lbl">Portfolio Value</div><div class="val mc-gold" id="s-total">--</div><div class="sub">USDT</div></div>
            <div class="bpm"><div class="lbl">Free USDT</div><div class="val mc-blue" id="s-usdt">--</div><div class="sub">Available</div></div>
            <div class="bpm"><div class="lbl">Total PnL</div><div class="val" id="s-pnl">--</div><div class="sub" id="s-pnl-pct">--</div></div>
          </div>
          <div class="dl-bar-wrap">
            <div class="dl-bar-row"><span>Daily Loss</span><span id="dl-text">--</span></div>
            <div class="dl-bar"><div id="dl-fill" class="dl-fill" style="width:0;background:var(--green)"></div></div>
          </div>
        </div>
        <!-- Futures -->
        <div class="bal-panel fut-panel">
          <div class="bp-header">
            <div class="bp-title fut">⚡ FUTURES</div>
            <span class="bp-tag badge-purp">× <span id="lev-disp">--</span></span>
          </div>
          <div class="bp-metrics">
            <div class="bpm"><div class="lbl">Balance</div><div class="val mc-gold" id="f-total">--</div><div class="sub">USDT</div></div>
            <div class="bpm"><div class="lbl">Positions</div><div class="val mc-purp" id="f-pos">0</div><div class="sub">Open</div></div>
            <div class="bpm"><div class="lbl">Unrealized</div><div class="val" id="f-pnl">--</div><div class="sub" id="f-pnl-pct">--</div></div>
          </div>
          <div id="fut-holdings"></div>
        </div>
      </div>

      <!-- Stat Cards -->
      <div class="g6 mb16">
        <div class="metric-card"><div class="mc-icon">📊</div><div class="mc-lbl">Total Trades</div><div class="mc-val mc-gold" id="st-total">0</div><div class="mc-sub">All time</div></div>
        <div class="metric-card"><div class="mc-icon">🎯</div><div class="mc-lbl">Win Rate</div><div class="mc-val" id="st-wr">0%</div><div class="mc-sub" id="st-wl">0W / 0L</div></div>
        <div class="metric-card"><div class="mc-icon">💰</div><div class="mc-lbl">Net PnL</div><div class="mc-val" id="st-pnl">$0.00</div><div class="mc-sub">Realized</div></div>
        <div class="metric-card"><div class="mc-icon">⚡</div><div class="mc-lbl">Profit Factor</div><div class="mc-val mc-blue" id="st-pf">--</div><div class="mc-sub">Gross P / Gross L</div></div>
        <div class="metric-card"><div class="mc-icon">📉</div><div class="mc-lbl">Max Drawdown</div><div class="mc-val mc-red" id="st-dd">$0</div><div class="mc-sub">Peak to trough</div></div>
        <div class="metric-card"><div class="mc-icon">🏆</div><div class="mc-lbl">Best Trade</div><div class="mc-val mc-green" id="st-best">--</div><div class="mc-sub">Single trade</div></div>
      </div>

      <!-- Equity Curve -->
      <div class="card mb16">
        <div class="card-head"><span class="card-title">📈 Equity Curve</span><span class="card-badge badge-gold" id="eq-balance">--</span></div>
        <div class="chart-wrap"><canvas id="equityCanvas"></canvas></div>
      </div>

      <!-- Recent Trades (last 10) -->
      <div class="card">
        <div class="card-head">
          <span class="card-title">⚡ Recent Trades</span>
          <button class="btn btn-ghost" style="font-size:10px;padding:4px 10px" onclick="switchTab('trades',document.querySelectorAll('.tab')[3])">View All →</button>
        </div>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>Date</th><th>Time</th><th>Mkt</th><th>Pair</th><th>Type</th><th>Price</th><th>Total</th><th>PnL $</th><th>Reason</th></tr></thead>
            <tbody id="recent-tbody"><tr><td colspan="9"><div class="empty-state"><span class="ei">📡</span><span class="et">Waiting for signals...</span></div></td></tr></tbody>
          </table>
        </div>
      </div>
    </div><!-- /overview -->

    <!-- ══════ ANALYTICS ══════ -->
    <div id="tab-analytics" class="panel">
      <!-- Period Selector -->
      <div class="abar mb16">
        <span style="font-size:11px;color:var(--t2);font-family:var(--mono)">Report Period:</span>
        <div class="period-tabs">
          <div class="period-tab active" onclick="setPeriod(24,this)">24H</div>
          <div class="period-tab" onclick="setPeriod(72,this)">3D</div>
          <div class="period-tab" onclick="setPeriod(168,this)">7D</div>
          <div class="period-tab" onclick="setPeriod(720,this)">30D</div>
          <div class="period-tab" onclick="setPeriod(99999,this)">All</div>
        </div>
      </div>

      <!-- Period Stats -->
      <div class="g4 mb16" id="period-cards">
        <div class="metric-card"><div class="mc-lbl">Trades</div><div class="mc-val mc-gold" id="p-trades">0</div></div>
        <div class="metric-card"><div class="mc-lbl">Win Rate</div><div class="mc-val" id="p-wr">0%</div></div>
        <div class="metric-card"><div class="mc-lbl">PnL</div><div class="mc-val" id="p-pnl">$0</div></div>
        <div class="metric-card"><div class="mc-lbl">W / L</div><div class="mc-val mc-muted" id="p-wl">0 / 0</div></div>
      </div>

      <!-- Advanced Stats -->
      <div class="g2 mb16">
        <div class="card">
          <div class="card-head"><span class="card-title">📊 Performance Metrics</span></div>
          <div style="padding:16px 20px">
            <div class="stat-row"><span class="stat-lbl">Sharpe Ratio</span><span class="stat-val" id="a-sharpe">--</span></div>
            <div class="stat-row"><span class="stat-lbl">Profit Factor</span><span class="stat-val" id="a-pf">--</span></div>
            <div class="stat-row"><span class="stat-lbl">Expectancy</span><span class="stat-val" id="a-exp">--</span></div>
            <div class="stat-row"><span class="stat-lbl">Avg Win</span><span class="stat-val mc-green" id="a-avgwin">--</span></div>
            <div class="stat-row"><span class="stat-lbl">Avg Loss</span><span class="stat-val mc-red" id="a-avgloss">--</span></div>
            <div class="stat-row"><span class="stat-lbl">Max Consecutive Wins</span><span class="stat-val mc-green" id="a-cwin">--</span></div>
            <div class="stat-row"><span class="stat-lbl">Max Consecutive Losses</span><span class="stat-val mc-red" id="a-closs">--</span></div>
          </div>
        </div>
        <div class="card">
          <div class="card-head"><span class="card-title">💵 PnL Breakdown</span></div>
          <div style="padding:16px 20px">
            <div class="stat-row"><span class="stat-lbl">Gross Profit</span><span class="stat-val mc-green" id="a-gp">--</span></div>
            <div class="stat-row"><span class="stat-lbl">Gross Loss</span><span class="stat-val mc-red" id="a-gl">--</span></div>
            <div class="stat-row"><span class="stat-lbl">Net PnL</span><span class="stat-val" id="a-net">--</span></div>
            <div class="stat-row"><span class="stat-lbl">Max Drawdown</span><span class="stat-val mc-red" id="a-dd">--</span></div>
            <div class="stat-row"><span class="stat-lbl">Best Trade</span><span class="stat-val mc-green" id="a-best">--</span></div>
            <div class="stat-row"><span class="stat-lbl">Worst Trade</span><span class="stat-val mc-red" id="a-worst">--</span></div>
            <div class="stat-row"><span class="stat-lbl">Total Trades</span><span class="stat-val mc-gold" id="a-total">--</span></div>
          </div>
        </div>
      </div>

      <!-- Equity Curve Full -->
      <div class="card mb16">
        <div class="card-head"><span class="card-title">📈 Portfolio Growth</span><span class="card-badge badge-gold" id="eq-bal2">--</span></div>
        <div class="chart-wrap"><canvas id="equityCanvas2" style="height:260px"></canvas></div>
      </div>

      <!-- Trade Distribution Chart -->
      <div class="card">
        <div class="card-head"><span class="card-title">🎯 Trade Results Distribution</span></div>
        <div class="chart-wrap"><canvas id="distCanvas" style="height:180px"></canvas></div>
      </div>
    </div><!-- /analytics -->

    <!-- ══════ PORTFOLIO ══════ -->
    <div id="tab-portfolio" class="panel">
      <div class="card">
        <div class="card-head">
          <span class="card-title">💼 Current Holdings</span>
          <span class="card-badge badge-gold" id="port-count">0 coins</span>
        </div>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>Coin</th><th>Amount</th><th>Buy Price</th><th>Current</th><th>Value $</th><th>PnL $</th><th>PnL %</th><th>Allocation</th></tr></thead>
            <tbody id="port-tbody"><tr><td colspan="8"><div class="empty-state"><span class="ei">💼</span><span class="et">No positions held</span></div></td></tr></tbody>
          </table>
        </div>
      </div>
    </div><!-- /portfolio -->

    <!-- ══════ TRADE PAIRS ══════ -->
    <div id="tab-tradepairs" class="panel">

      <!-- Summary Bar -->
      <div class="g4 mb16" id="tp-summary-cards">
        <div class="metric-card"><div class="mc-icon">🔗</div><div class="mc-lbl">Total Pairs</div><div class="mc-val mc-gold" id="tp-total">0</div><div class="mc-sub">All trades</div></div>
        <div class="metric-card"><div class="mc-icon">🟢</div><div class="mc-lbl">Open Now</div><div class="mc-val mc-blue" id="tp-open">0</div><div class="mc-sub">Unrealized</div></div>
        <div class="metric-card"><div class="mc-icon">✅</div><div class="mc-lbl">Closed</div><div class="mc-val mc-green" id="tp-closed">0</div><div class="mc-sub">Realized</div></div>
        <div class="metric-card"><div class="mc-icon">💰</div><div class="mc-lbl">Realized PnL</div><div class="mc-val" id="tp-pnl">$0</div><div class="mc-sub">Closed only</div></div>
      </div>

      <!-- Filter Bar -->
      <div class="abar mb12">
        <select class="sel-input" id="tp-filter-market" onchange="renderTradePairs()">
          <option value="">All Markets</option>
          <option value="SPOT">Spot</option>
          <option value="FUTURES">Futures</option>
        </select>
        <select class="sel-input" id="tp-filter-status" onchange="renderTradePairs()">
          <option value="">All Status</option>
          <option value="OPEN">Open 🟢</option>
          <option value="CLOSED">Closed ✅</option>
        </select>
        <input class="n-input" type="text" id="tp-filter-pair" placeholder="Pair..." oninput="renderTradePairs()" style="width:100px;text-align:left">
        <select class="sel-input" id="tp-filter-result" onchange="renderTradePairs()">
          <option value="">All Results</option>
          <option value="win">Profit ✅</option>
          <option value="loss">Loss ❌</option>
        </select>
        <button class="btn btn-ghost" onclick="clearTpFilters()">Clear</button>
        <div class="adiv"></div>
        <span style="font-family:var(--mono);font-size:10px;color:var(--t2)" id="tp-count-info">-- pairs</span>
      </div>

      <!-- Table -->
      <div class="card">
        <div class="tbl-wrap">
          <table id="tp-table">
            <thead><tr>
              <th>Status</th>
              <th>Market</th>
              <th>Pair</th>
              <th>Side</th>
              <th>📅 Buy Date</th>
              <th>Buy Price</th>
              <th>Buy Total</th>
              <th>📅 Sell Date</th>
              <th>Sell Price</th>
              <th>Change</th>
              <th>PnL $</th>
              <th>PnL %</th>
              <th>Duration</th>
              <th>Reason</th>
            </tr></thead>
            <tbody id="tp-tbody">
              <tr><td colspan="14"><div class="empty-state"><span class="ei">🔗</span><span class="et">No trade pairs yet — pairs appear after first buy signal</span></div></td></tr>
            </tbody>
          </table>
        </div>
      </div>

    </div><!-- /tradepairs -->

    <!-- ══════ TRADES ══════ -->
    <div id="tab-trades" class="panel">
      <!-- Filters -->
      <div class="abar mb12">
        <select class="sel-input" id="filter-market" onchange="filterTrades()">
          <option value="">All Markets</option>
          <option value="SPOT">Spot</option>
          <option value="FUTURES">Futures</option>
        </select>
        <select class="sel-input" id="filter-type" onchange="filterTrades()">
          <option value="">All Types</option>
          <option value="buy">Buy</option>
          <option value="sell">Sell</option>
          <option value="long_open">Long Open</option>
          <option value="long_close">Long Close</option>
          <option value="short_open">Short Open</option>
          <option value="short_close">Short Close</option>
        </select>
        <input class="n-input" type="text" id="filter-pair" placeholder="Pair..." oninput="filterTrades()" style="width:100px;text-align:left">
        <button class="btn btn-ghost" onclick="clearFilters()">Clear</button>
        <div class="adiv"></div>
        <span style="font-family:var(--mono);font-size:10px;color:var(--t2)" id="trade-count-info">-- trades</span>
      </div>
      <div class="card">
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>Date</th><th>Time</th><th>Mkt</th><th>Pair</th><th>Type</th><th>Qty</th><th>Price</th><th>Total</th><th>PnL $</th><th>PnL %</th><th>Reason</th><th>Status</th></tr></thead>
            <tbody id="all-tbody"><tr><td colspan="12"><div class="empty-state"><span class="ei">📡</span><span class="et">Waiting for signals...</span></div></td></tr></tbody>
          </table>
        </div>
      </div>
    </div><!-- /trades -->

    <!-- ══════ SETTINGS ══════ -->
    <div id="tab-settings" class="panel">
      <div class="settings-grid">

        <!-- Spot -->
        <div class="s-group">
          <div class="s-group-title">💧 SPOT</div>
          <div class="s-row"><div><div class="s-lbl">Buy Mode</div></div>
            <select class="sel-input" id="s-buy-mode" onchange="ss('spot_buy_mode',this.value)">
              <option value="fixed">Fixed $</option>
              <option value="percent">Percent %</option>
            </select>
          </div>
          <div class="s-row"><div class="s-lbl">Buy Value</div><input class="n-input" id="s-buy-val" type="number" min="11" onchange="ss('spot_buy_value',+this.value)"></div>
          <div class="s-row"><div class="s-lbl">Sell Ratio (1=100%)</div><input class="n-input" id="s-sell-r" type="number" min="0.1" max="1" step="0.1" onchange="ss('spot_sell_ratio',+this.value)"></div>
          <div class="s-row"><div class="s-lbl">Max Positions</div><input class="n-input" id="s-max-pos" type="number" min="1" max="20" onchange="ss('spot_max_positions',+this.value)"></div>
        </div>

        <!-- Futures -->
        <div class="s-group">
          <div class="s-group-title">⚡ FUTURES</div>
          <div class="s-row"><div class="s-lbl">Enable Futures</div><label class="toggle"><input type="checkbox" id="fut-en" onchange="ss('futures_enabled',this.checked)"><span class="tgl-slider"></span></label></div>
          <div class="s-row"><div class="s-lbl">Position Size $</div><input class="n-input" id="f-val" type="number" min="11" onchange="ss('futures_value',+this.value)"></div>
          <div class="s-row"><div class="s-lbl">Leverage ×</div><input class="n-input" id="lev-in" type="number" min="1" max="125" onchange="ss('leverage',+this.value)"></div>
          <div class="s-row"><div class="s-lbl">Max Positions</div><input class="n-input" id="f-max-pos" type="number" min="1" max="10" onchange="ss('futures_max_positions',+this.value)"></div>
        </div>

        <!-- Risk -->
        <div class="s-group">
          <div class="s-group-title">🛡️ RISK MANAGEMENT</div>
          <div class="s-row"><div class="s-lbl">Enable Risk Mgmt</div><label class="toggle"><input type="checkbox" id="risk-en" onchange="ss('risk_enabled',this.checked)"><span class="tgl-slider"></span></label></div>
          <div class="s-row"><div class="s-lbl">Trailing Stop %</div><input class="n-input" id="trail-pct" type="number" min="0.1" max="20" step="0.1" onchange="ss('trailing_stop_pct',+this.value)"></div>
          <div class="s-row"><div class="s-lbl">Fixed Stop Loss %</div><input class="n-input" id="fsl-pct" type="number" min="0.1" max="50" step="0.1" onchange="ss('fixed_stop_loss_pct',+this.value)"></div>
        </div>

        <!-- Position Sizing -->
        <div class="s-group">
          <div class="s-group-title">📐 POSITION SIZING</div>
          <div class="s-row"><div class="s-lbl">Auto Sizing</div><label class="toggle"><input type="checkbox" id="ps-en" onchange="ss('position_sizing_enabled',this.checked)"><span class="tgl-slider"></span></label></div>
          <div class="s-row"><div class="s-lbl">Size % of Portfolio</div><input class="n-input" id="ps-pct" type="number" min="1" max="50" step="0.5" onchange="ss('position_sizing_pct',+this.value)"></div>
          <div class="s-row"><div class="s-lbl">Max Concentration %</div><input class="n-input" id="max-conc" type="number" min="5" max="100" step="5" onchange="ss('max_concentration_pct',+this.value)"></div>
        </div>

        <!-- Daily Loss -->
        <div class="s-group">
          <div class="s-group-title">🚦 DAILY LOSS LIMIT</div>
          <div class="s-row"><div class="s-lbl">Enable</div><label class="toggle"><input type="checkbox" id="dl-en" onchange="ss('daily_loss_enabled',this.checked)"><span class="tgl-slider"></span></label></div>
          <div class="s-row"><div class="s-lbl">Limit %</div><input class="n-input" id="dl-pct" type="number" min="0.5" max="50" step="0.5" onchange="ss('daily_loss_limit_pct',+this.value)"></div>
        </div>

        <!-- Session -->
        <div class="s-group">
          <div class="s-group-title">⏰ SESSION MANAGER</div>
          <div class="s-row"><div class="s-lbl">Enable</div><label class="toggle"><input type="checkbox" id="sess-en" onchange="ss('session_enabled',this.checked)"><span class="tgl-slider"></span></label></div>
          <div class="s-row"><div class="s-lbl">Start</div><input class="n-input" id="sess-s" type="time" onchange="ss('session_start',this.value)"></div>
          <div class="s-row"><div class="s-lbl">End</div><input class="n-input" id="sess-e" type="time" onchange="ss('session_end',this.value)"></div>
        </div>

        <!-- Calendar -->
        <div class="s-group">
          <div class="s-group-title">📅 ECONOMIC CALENDAR</div>
          <div class="s-row"><div class="s-lbl">Enable</div><label class="toggle"><input type="checkbox" id="cal-en" onchange="ss('calendar_enabled',this.checked)"><span class="tgl-slider"></span></label></div>
          <div class="s-row"><div class="s-lbl">Pause Before (min)</div><input class="n-input" id="cal-b" type="number" min="5" max="120" onchange="ss('calendar_pause_before',+this.value)"></div>
          <div class="s-row"><div class="s-lbl">Resume After (min)</div><input class="n-input" id="cal-a" type="number" min="5" max="180" onchange="ss('calendar_resume_after',+this.value)"></div>
        </div>

        <!-- Notifications -->
        <div class="s-group">
          <div class="s-group-title">🔔 NOTIFICATIONS</div>
          <div class="s-row"><div class="s-lbl">Sound Alerts</div><label class="toggle"><input type="checkbox" id="snd-en" onchange="ss('sound_enabled',this.checked)"><span class="tgl-slider"></span></label></div>
          <div class="s-row"><div class="s-lbl">Toast Popups</div><label class="toggle"><input type="checkbox" id="toast-en" onchange="ss('toast_enabled',this.checked)"><span class="tgl-slider"></span></label></div>
        </div>

        <!-- Telegram -->
        <div class="s-group">
          <div class="s-group-title">📲 TELEGRAM</div>
          <div class="s-row"><div class="s-lbl">Enable</div><label class="toggle"><input type="checkbox" id="tg-en" onchange="ss('telegram_enabled',this.checked)"><span class="tgl-slider"></span></label></div>
          <div class="s-row"><div class="s-lbl">On Trade</div><label class="toggle"><input type="checkbox" id="tg-trade" onchange="ss('telegram_on_trade',this.checked)"><span class="tgl-slider"></span></label></div>
          <div class="s-row"><div class="s-lbl">On Error</div><label class="toggle"><input type="checkbox" id="tg-err" onchange="ss('telegram_on_error',this.checked)"><span class="tgl-slider"></span></label></div>
          <div class="s-row"><div class="s-lbl">Daily Report</div><label class="toggle"><input type="checkbox" id="tg-rep" onchange="ss('telegram_daily_report',this.checked)"><span class="tgl-slider"></span></label></div>
          <div class="s-row"><div class="s-lbl">Report Time</div><input class="n-input" id="tg-time" type="time" onchange="ss('telegram_report_time',this.value)"></div>
        </div>

      </div>
    </div><!-- /settings -->

    <!-- ══════ MOVERS ══════ -->
    <div id="tab-movers" class="panel">
      <div class="abar mb16">
        <span style="font-family:var(--mono);font-size:10px;color:var(--t2)">🔥 Top Volatile Coins — 24H</span>
        <button class="btn btn-blue" onclick="loadMovers()">🔄 Refresh</button>
      </div>
      <div class="g5" id="movers-grid">
        <div class="empty-state" style="grid-column:1/-1"><span class="ei">🔥</span><span class="et">Click Refresh to load</span></div>
      </div>
    </div><!-- /movers -->

    <!-- ══════ SECURITY ══════ -->
    <div id="tab-security" class="panel">
      <div class="card">
        <div class="card-head">
          <span class="card-title">🔒 Login History</span>
          <span class="card-badge badge-gold" id="login-count">0 entries</span>
        </div>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>Date</th><th>Time</th><th>IP Address</th><th>Status</th><th>User Agent</th></tr></thead>
            <tbody id="login-tbody"><tr><td colspan="5"><div class="empty-state"><span class="ei">🔒</span><span class="et">No login history</span></div></td></tr></tbody>
          </table>
        </div>
      </div>

      <div style="margin-top:12px" class="card">
        <div class="card-head"><span class="card-title">🗂️ Error Log</span><button class="btn btn-ghost" onclick="clearErrors()" style="font-size:10px;padding:4px 10px">Clear All</button></div>
        <div id="error-list"><div class="empty-state"><span class="ei">✅</span><span class="et">No errors</span></div></div>
      </div>
    </div><!-- /security -->

  </div><!-- /wrap -->

    <!-- AI AGENTS PANEL -->
    <div id="tab-agents" class="panel">

      <div class="abar mb16">
        <span style="font-family:var(--mono);font-size:10px;color:var(--t2)">🤖 Sovereign Agents — Intelligence Hub</span>
        <button class="btn btn-blue" onclick="loadAgents()">🔄 Refresh</button>
        <span style="font-family:var(--mono);font-size:10px;color:var(--t3)" id="agents-updated"></span>
      </div>

      <!-- Agent Health -->
      <div class="g6 mb16" id="agent-health-grid">
        <div class="metric-card"><div class="mc-lbl">Loading...</div></div>
      </div>

      <!-- Optimizer Running Bar -->
      <div class="card mb16" id="optimizer-status-card" style="display:none">
        <div class="card-head">
          <span class="card-title">⚙️ Optimizer Running...</span>
          <span class="card-badge badge-gold" id="opt-progress">0%</span>
        </div>
        <div style="padding:10px 20px">
          <div class="dl-bar"><div id="opt-bar" class="dl-fill" style="width:0;background:var(--gold);transition:width 1s"></div></div>
          <div style="font-family:var(--mono);font-size:10px;color:var(--t2);margin-top:6px" id="opt-symbol">Analyzing...</div>
        </div>
      </div>

      <!-- Optimizer Results -->
      <div class="card mb16">
        <div class="card-head">
          <span class="card-title">🎯 Optimizer Results — Best Settings Per Coin</span>
          <span class="card-badge badge-gold" id="opt-last-run">Not run yet</span>
        </div>
        <div id="opt-results-body" style="padding:16px 20px">
          <div class="empty-state"><span class="ei">⚙️</span><span class="et">Optimizer runs every 24h — results appear here</span></div>
        </div>
      </div>

      <!-- Market Signals + Risk -->
      <div class="g2 mb16">
        <div class="card">
          <div class="card-head"><span class="card-title">📊 Market Signals</span><span class="card-badge badge-gold" id="ag-market-regime">--</span></div>
          <div id="ag-signals-body" style="padding:16px 20px">
            <div class="empty-state"><span class="ei">⏳</span><span class="et">Loading...</span></div>
          </div>
        </div>
        <div class="card">
          <div class="card-head"><span class="card-title">🛡️ Risk Monitor</span><span class="card-badge" id="ag-risk-badge">--</span></div>
          <div id="ag-risk-body" style="padding:16px 20px">
            <div class="empty-state"><span class="ei">⏳</span><span class="et">Loading...</span></div>
          </div>
        </div>
      </div>

      <!-- Agent Events -->
      <div class="card">
        <div class="card-head">
          <span class="card-title">⚡ Agent Events</span>
          <span class="card-badge badge-blue" id="ag-events-count">0</span>
        </div>
        <div class="tbl-wrap">
          <table>
            <thead><tr><th>Time</th><th>Agent</th><th>Type</th><th>Message</th><th>Priority</th></tr></thead>
            <tbody id="ag-events-tbody">
              <tr><td colspan="5"><div class="empty-state"><span class="ei">📡</span><span class="et">No events</span></div></td></tr>
            </tbody>
          </table>
        </div>
      </div>

    </div><!-- /agents -->

  <div class="footer">SOVEREIGN V8.0 · SPOT + FUTURES · AI TRADING SYSTEM</div>
</div><!-- /app -->

<!-- ══ MODAL: EXCEL ══ -->
<div id="excelModal" class="modal">
  <div class="modal-box" style="max-width:360px;text-align:center">
    <button class="modal-close" onclick="closeModal('excelModal')">✕</button>
    <div class="modal-title">📊 EXPORT EXCEL</div>
    <p style="color:var(--t2);font-size:13px;margin-bottom:20px;line-height:1.6">Export all trades with dates, prices, and PnL data to Excel.</p>
    <button class="btn btn-gold" style="width:100%;justify-content:center;padding:13px" onclick="doExport()">⬇ Download Excel File</button>
  </div>
</div>

<script>
// ══════════════════════════════════════════
// STATE
// ══════════════════════════════════════════
let lastData = null;
let allTrades = [];
let wsDelay = 2000;
let seenIds = new Set();
let shownToasts = new Set();
const SOUNDS = {
  buy:  new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivsJBzYF2As9j/zbOVhIqc0///8O/z9/f38+3j1tDMycjIxsTCwL69vby7u7u8vL29vb6+vr6+v7+/wMDAwMHBwcHBwcHBwcHBwcHBwcHCwsLCwsLCwsLCwsLCwsLCwsLCwsLCwsLCwsLCwsLCw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PDw8PD'),
};

// ══════════════════════════════════════════
// LOGIN
// ══════════════════════════════════════════
function doLogin() {
  const pw = document.getElementById('pwInput').value.trim();
  if (!pw) return;
  fetch('/auth/login', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({password:pw})
  }).then(r=>r.json()).then(d=>{
    if (d.ok) { sessionStorage.setItem('sv8','1'); showApp(); }
    else {
      const e = document.getElementById('loginErr');
      e.style.display = 'block';
      document.getElementById('pwInput').value = '';
      setTimeout(()=>e.style.display='none', 3000);
    }
  }).catch(()=>showApp());
}
function showApp() {
  document.getElementById('loginPage').style.display = 'none';
  document.getElementById('app').style.display = 'block';
  connect();
}
if (sessionStorage.getItem('sv8')==='1') showApp();

// ══════════════════════════════════════════
// WEBSOCKET
// ══════════════════════════════════════════
function connect() {
  const proto = location.protocol==='https:'?'wss:':'ws:';
  const ws = new WebSocket(proto+'//'+location.host+'/ws');
  ws.onopen = ()=>{
    document.getElementById('connDot').className = 'conn-dot live';
    document.getElementById('connTxt').textContent = 'Live · Connected';
    wsDelay = 2000;
  };
  ws.onmessage = e=>{
    lastData = JSON.parse(e.data);
    allTrades = lastData.trades || [];
    allTradePairs = lastData.trade_pairs || [];
    render(lastData);
  };
  ws.onclose = ()=>{
    document.getElementById('connDot').className = 'conn-dot';
    document.getElementById('connTxt').textContent = 'Reconnecting...';
    setTimeout(connect, wsDelay);
    wsDelay = Math.min(wsDelay*1.5, 30000);
  };
  ws.onerror = ()=>ws.close();
}

// ══════════════════════════════════════════
// HELPERS
// ══════════════════════════════════════════
const f = (n,d=2)=>Number(n||0).toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d});
const sg = v=>v>0?'+':'';
const pc = v=>v>0?'pnl-pos':v<0?'pnl-neg':'pnl-nil';
const reasonMap = {stop_loss:'🛑 SL', peak_exit:'🎯 Peak', trailing_stop:'📉 Trail'};
const tbMap = {
  buy:        '<span class="tb tb-buy">BUY</span>',
  sell:       '<span class="tb tb-sell">SELL</span>',
  long_open:  '<span class="tb tb-long">LONG ▲</span>',
  long_close: '<span class="tb tb-lclose">▼ Close L</span>',
  short_open: '<span class="tb tb-short">SHORT ▼</span>',
  short_close:'<span class="tb tb-sclose">▲ Close S</span>',
};

function pnlHtml(v, pct) {
  if (v===0&&(pct===undefined||pct===0)) return '<span class="pnl-nil">—</span>';
  const c = pc(v);
  const p = pct!==undefined ? ` <span style="font-size:10px">(${sg(pct)}${pct}%)</span>` : '';
  return `<span class="${c}">${sg(v)}${f(v)}$${p}</span>`;
}

// ══════════════════════════════════════════
// MAIN RENDER
// ══════════════════════════════════════════
function render(d) {
  document.getElementById('last-upd').textContent = new Date().toLocaleTimeString();
  const s = d.settings || {};
  syncSettings(s);
  renderState(s);

  // Topbar
  const sp = d.spot || {};
  const fp = d.futures || {};
  const st = d.stats || {};
  const allPos = Object.keys(sp.holdings||{}).length + Object.keys(fp.holdings||{}).length;
  document.getElementById('tb-total').textContent = '$'+f(sp.total||0);
  const tbPnl = document.getElementById('tb-pnl');
  const tp = sp.pnl||0;
  tbPnl.textContent = (tp>=0?'+':'')+f(tp)+'$';
  tbPnl.className = 'val '+(tp>=0?'mc-green':'mc-red');
  document.getElementById('tb-wr').textContent = (st.win_rate||0)+'%';
  document.getElementById('tb-open').textContent = allPos;

  // Spot Balance
  document.getElementById('s-total').textContent = f(sp.total||0);
  document.getElementById('s-usdt').textContent  = f(sp.usdt||0);
  const spnl = sp.pnl||0;
  const sEl  = document.getElementById('s-pnl');
  sEl.textContent = sg(spnl)+f(spnl)+'$';
  sEl.className   = 'val '+( spnl>=0?'mc-green':'mc-red' );
  document.getElementById('s-pnl-pct').textContent = sg(spnl)+(sp.pnl_pct||0)+'%';

  // Daily Loss
  const dl = d.daily_loss || {};
  const dlCur = Math.abs(dl.current||0), dlLim = dl.limit||1;
  const dlPct = Math.min((dlCur/dlLim)*100,100);
  document.getElementById('dl-text').textContent   = `${f(dlCur)}$ / ${f(dlLim)}$`;
  document.getElementById('dl-ticker').textContent = `${f(dlCur)}$ / ${f(dlLim)}$`;
  const fill = document.getElementById('dl-fill');
  fill.style.width = dlPct+'%';
  fill.style.background = dlPct>80?'var(--red)':dlPct>50?'var(--orange)':'var(--green)';

  // Futures
  document.getElementById('f-total').textContent = f(fp.total||0);
  document.getElementById('f-pos').textContent   = Object.keys(fp.holdings||{}).length;
  document.getElementById('lev-disp').textContent = (s.leverage||'--')+'x';
  const fpnl = fp.pnl||0;
  const fEl  = document.getElementById('f-pnl');
  fEl.textContent = sg(fpnl)+f(fpnl)+'$';
  fEl.className   = 'val '+(fpnl>=0?'mc-green':'mc-red');
  document.getElementById('f-pnl-pct').textContent = sg(fpnl)+(fp.pnl_pct||0)+'%';

  // Futures Positions
  renderFuturesPositions(fp.holdings||{});

  // Calendar
  const calEv = s.calendar_next_event||'';
  const calTk = document.getElementById('cal-ticker');
  const calSp = document.getElementById('cal-sep');
  if (calEv && s.calendar_enabled) {
    calTk.textContent = `${calEv} — ${s.calendar_next_event_time}`;
    calTk.style.display=''; calSp.style.display='';
  } else {
    calTk.style.display='none'; calSp.style.display='none';
  }

  // Stats
  document.getElementById('st-total').textContent = st.total||0;
  document.getElementById('st-wr').textContent    = (st.win_rate||0)+'%';
  document.getElementById('st-wr').className      = 'mc-val '+(st.win_rate>=50?'mc-green':st.win_rate>=30?mc-gold:'mc-red');
  document.getElementById('st-wl').textContent    = `${st.wins||0}W / ${st.losses||0}L`;
  const pnlEl = document.getElementById('st-pnl');
  const tp2   = st.total_pnl||0;
  pnlEl.textContent = (tp2>=0?'+':'')+f(tp2)+'$';
  pnlEl.className   = 'mc-val '+(tp2>=0?'mc-green':'mc-red');
  document.getElementById('st-pf').textContent   = st.profit_factor||'--';
  document.getElementById('st-dd').textContent   = '-$'+f(st.max_drawdown||0);
  document.getElementById('st-best').textContent = (st.best_trade>0?'+':'')+f(st.best_trade||0)+'$';

  // Analytics
  document.getElementById('a-sharpe').textContent  = st.sharpe||'--';
  document.getElementById('a-sharpe').className    = 'stat-val '+((st.sharpe||0)>=1?'mc-green':(st.sharpe||0)>=0?'mc-gold':'mc-red');
  document.getElementById('a-pf').textContent      = st.profit_factor||'--';
  document.getElementById('a-exp').textContent     = (st.expectancy>0?'+':'')+f(st.expectancy||0)+'$';
  document.getElementById('a-avgwin').textContent  = '+$'+f(st.avg_win||0);
  document.getElementById('a-avgloss').textContent = '$'+f(st.avg_loss||0);
  document.getElementById('a-cwin').textContent    = st.consecutive_wins||0;
  document.getElementById('a-closs').textContent   = st.consecutive_losses||0;
  document.getElementById('a-gp').textContent      = '+$'+f(st.gross_profit||0);
  document.getElementById('a-gl').textContent      = '-$'+f(st.gross_loss||0);
  const aNet = document.getElementById('a-net');
  const np   = st.total_pnl||0;
  aNet.textContent = (np>=0?'+':'')+f(np)+'$';
  aNet.className   = 'stat-val '+(np>=0?'mc-green':'mc-red');
  document.getElementById('a-dd').textContent    = '-$'+f(st.max_drawdown||0);
  document.getElementById('a-best').textContent  = '+$'+f(st.best_trade||0);
  document.getElementById('a-worst').textContent = '$'+f(st.worst_trade||0);
  document.getElementById('a-total').textContent = st.total||0;

  // Period stats
  const ps = d.period_stats||{};
  document.getElementById('p-trades').textContent = ps.trades||0;
  const pwEl = document.getElementById('p-wr');
  pwEl.textContent = (ps.win_rate||0)+'%';
  pwEl.className = 'mc-val '+((ps.win_rate||0)>=50?'mc-green':(ps.win_rate||0)>=30?'mc-gold':'mc-red');
  const ppEl = document.getElementById('p-pnl');
  const pp   = ps.pnl||0;
  ppEl.textContent = (pp>=0?'+':'')+f(pp)+'$';
  ppEl.className   = 'mc-val '+(pp>=0?'mc-green':'mc-red');
  document.getElementById('p-wl').textContent = `${ps.wins||0}W / ${ps.losses||0}L`;

  // Equity
  renderEquity(d.equity_curve||[], d.initial_balance||10000);

  // Portfolio
  renderPortfolio(sp.holdings||{}, sp.total||0);

  // Trades
  renderTrades(allTrades);
  renderRecentTrades(allTrades.slice(0,10));

  // Trade Pairs
  renderTradePairs();

  // Errors
  renderErrors(d.errors||[]);

  // Login logs
  renderLoginLogs(d.login_logs||[]);

  // Toasts
  if (d.toasts) renderToasts(d.toasts);
}

function renderFuturesPositions(holdings) {
  const el = document.getElementById('fut-holdings');
  const keys = Object.keys(holdings);
  if (!keys.length) { el.innerHTML=''; return; }
  el.innerHTML = `<div style="margin-top:12px;border-top:1px solid var(--border2)">
    <div style="padding:8px 0 4px;font-size:9px;color:var(--t2);font-family:var(--mono);text-transform:uppercase;letter-spacing:1px">Open Positions</div>
    ${keys.map(sym=>{
      const p = holdings[sym];
      return `<div class="pos-row">
        <span class="pos-sym">${sym}</span>
        <span class="pos-side ${p.side==='long'?'pos-long':'pos-short'}">${p.side}</span>
        <span style="font-family:var(--mono);color:var(--t2);font-size:10px">@${f(p.entry_price,4)}</span>
        <span style="font-family:var(--mono);font-size:10px;color:var(--blue)">${f(p.current_price,4)}</span>
        <span class="${pc(p.unrealized_pnl)}" style="font-size:11px;margin-right:auto">${sg(p.unrealized_pnl)}${f(p.unrealized_pnl)}$</span>
        <span class="${pc(p.pnl_pct)}" style="font-size:10px">${sg(p.pnl_pct)}${p.pnl_pct}%</span>
      </div>`;
    }).join('')}
  </div>`;
}

function renderPortfolio(holdings, total) {
  const keys = Object.keys(holdings);
  document.getElementById('port-count').textContent = keys.length+' coins';
  if (!keys.length) {
    document.getElementById('port-tbody').innerHTML = '<tr><td colspan="8"><div class="empty-state"><span class="ei">💼</span><span class="et">No positions held</span></div></td></tr>';
    return;
  }
  const sorted = keys.sort((a,b)=>(holdings[b].value||0)-(holdings[a].value||0));
  document.getElementById('port-tbody').innerHTML = sorted.map(c=>{
    const v = holdings[c];
    const alloc = total>0 ? ((v.value/total)*100).toFixed(1) : 0;
    const allocColor = alloc>30?'var(--orange)':alloc>20?'var(--gold)':'var(--green)';
    return `<tr>
      <td><div class="port-coin"><div class="coin-dot"></div><span class="coin-name">${c}</span></div></td>
      <td class="td-mono">${v.amount}</td>
      <td class="td-mono" style="color:var(--t2)">${f(v.buy_price,4)}</td>
      <td class="td-mono" style="color:var(--blue)">${f(v.current_price,4)}</td>
      <td class="td-mono" style="color:var(--gold)">${f(v.value,2)}$</td>
      <td>${pnlHtml(v.pnl_usd)}</td>
      <td>${pnlHtml(v.pnl_pct)}</td>
      <td>
        <div style="font-family:var(--mono);font-size:10px;color:${allocColor}">${alloc}%</div>
        <div class="conc-bar"><div class="conc-fill" style="width:${Math.min(alloc,100)}%;background:${allocColor}"></div></div>
      </td>
    </tr>`;
  }).join('');
}

function renderRecentTrades(trades) {
  if (!trades.length) { document.getElementById('recent-tbody').innerHTML='<tr><td colspan="9"><div class="empty-state"><span class="ei">📡</span><span class="et">Waiting for signals...</span></div></td></tr>'; return; }
  document.getElementById('recent-tbody').innerHTML = trades.map(t=>tradeRow(t,'recent')).join('');
}

function renderTrades(trades) {
  const fm = document.getElementById('filter-market').value;
  const ft = document.getElementById('filter-type').value;
  const fp = document.getElementById('filter-pair').value.toUpperCase();
  const filtered = trades.filter(t=>
    (!fm || t.market===fm) &&
    (!ft || t.act===ft) &&
    (!fp || t.pair.includes(fp))
  );
  document.getElementById('trade-count-info').textContent = filtered.length+' trades';
  if (!filtered.length) { document.getElementById('all-tbody').innerHTML='<tr><td colspan="12"><div class="empty-state"><span class="ei">🔍</span><span class="et">No matching trades</span></div></td></tr>'; return; }
  document.getElementById('all-tbody').innerHTML = filtered.map(t=>tradeRow(t,'full')).join('');
}

function tradeRow(t, mode) {
  const isNew = !seenIds.has(t.id);
  if (isNew) seenIds.add(t.id);
  const mkt  = t.market==='FUTURES'?'<span class="mkt-f">F</span>':'<span class="mkt-s">S</span>';
  const badge = tbMap[t.act] || `<span class="tb tb-sell">${t.act}</span>`;
  const isSell = ['sell','long_close','short_close'].includes(t.act);
  let pnlPct = '—';
  if (isSell && t.pnl!==0 && t.total>0) {
    const cost = (t.total||0)-(t.pnl||0);
    if (cost>0) pnlPct = `${sg(t.pnl/cost*100)}${f(t.pnl/cost*100,2)}%`;
  }
  if (mode==='recent') return `<tr class="${isNew?'flash-row':''}">
    <td class="td-muted">${t.date||'--'}</td>
    <td class="td-muted">${t.time}</td>
    <td>${mkt}</td>
    <td class="td-pair">${t.pair}</td>
    <td>${badge}</td>
    <td class="td-price">${t.price>0?f(t.price,4):'—'}</td>
    <td class="td-mono" style="color:var(--green)">${t.total>0?f(t.total,2)+'$':'—'}</td>
    <td>${isSell&&t.pnl!==0?pnlHtml(t.pnl):'<span class="pnl-nil">—</span>'}</td>
    <td class="reason-tag">${reasonMap[t.reason]||'—'}</td>
  </tr>`;
  return `<tr class="${isNew?'flash-row':''}">
    <td class="td-muted">${t.date||'--'}</td>
    <td class="td-muted">${t.time}</td>
    <td>${mkt}</td>
    <td class="td-pair">${t.pair}</td>
    <td>${badge}</td>
    <td class="td-mono">${t.amount>0?t.amount:'—'}</td>
    <td class="td-price">${t.price>0?f(t.price,4):'—'}</td>
    <td class="td-mono" style="color:var(--gold)">${t.total>0?f(t.total,2)+'$':'—'}</td>
    <td>${isSell&&t.pnl!==0?pnlHtml(t.pnl):'<span class="pnl-nil">—</span>'}</td>
    <td>${isSell&&t.pnl!==0?`<span class="${pc(t.pnl)}">${pnlPct}</span>`:'<span class="pnl-nil">—</span>'}</td>
    <td class="reason-tag">${reasonMap[t.reason]||'—'}</td>
    <td>${t.success?'<span style="color:var(--green);font-size:10px">✅</span>':'<span style="color:var(--red);font-size:10px" title="'+t.err+'">❌</span>'}</td>
  </tr>`;
}

function renderErrors(errs) {
  const el = document.getElementById('error-list');
  if (!errs.length) { el.innerHTML='<div class="empty-state"><span class="ei">✅</span><span class="et">No errors logged</span></div>'; return; }
  el.innerHTML = errs.map(e=>`<div style="display:flex;gap:12px;padding:10px 18px;border-bottom:1px solid var(--border2)">
    <span style="color:var(--t3);font-size:9px;font-family:var(--mono);white-space:nowrap;margin-top:1px">${e.date} ${e.time}</span>
    <span style="color:var(--red);font-family:var(--mono);font-size:11px;word-break:break-all">❌ ${e.msg}</span>
  </div>`).join('');
}

function renderLoginLogs(logs) {
  document.getElementById('login-count').textContent = logs.length+' entries';
  if (!logs.length) { document.getElementById('login-tbody').innerHTML='<tr><td colspan="5"><div class="empty-state"><span class="ei">🔒</span><span class="et">No login history</span></div></td></tr>'; return; }
  document.getElementById('login-tbody').innerHTML = logs.map(l=>`<tr>
    <td class="td-muted">${l.date}</td>
    <td class="td-muted">${l.time}</td>
    <td class="td-mono" style="color:var(--blue)">${l.ip}</td>
    <td><span style="font-family:var(--mono);font-size:11px;color:${l.status.includes('✅')?'var(--green)':'var(--red)'}">${l.status}</span></td>
    <td class="td-muted" style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${l.ua}</td>
  </tr>`).join('');
}

// ══════════════════════════════════════════
// EQUITY CHART
// ══════════════════════════════════════════
function renderEquity(curve, initBal) {
  const val = initBal + curve.reduce((s,c)=>s+(c.value-initBal>0?c.value-initBal:0),0);
  document.getElementById('eq-balance').textContent = '$'+f(curve.length?curve[curve.length-1].value:initBal);
  if (document.getElementById('eq-bal2'))
    document.getElementById('eq-bal2').textContent = '$'+f(curve.length?curve[curve.length-1].value:initBal);
  ['equityCanvas','equityCanvas2'].forEach(id=>{
    const canvas = document.getElementById(id);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.offsetWidth || 600;
    const H = canvas.offsetHeight || 200;
    canvas.width = W * devicePixelRatio;
    canvas.height = H * devicePixelRatio;
    ctx.scale(devicePixelRatio, devicePixelRatio);
    ctx.clearRect(0,0,W,H);
    if (!curve.length) {
      ctx.fillStyle='rgba(255,255,255,.04)';
      ctx.fillRect(0,0,W,H);
      ctx.fillStyle='rgba(255,255,255,.1)';
      ctx.font='11px IBM Plex Mono';
      ctx.textAlign='center';
      ctx.fillText('No trades yet — equity curve will appear after first closed trade', W/2, H/2);
      return;
    }
    const vals = curve.map(c=>c.value);
    const minV = Math.min(...vals, initBal);
    const maxV = Math.max(...vals, initBal);
    const range = maxV-minV || 1;
    const pad = {t:20,b:30,l:60,r:16};
    const cW = W-pad.l-pad.r;
    const cH = H-pad.t-pad.b;
    const xOf = i=>pad.l + (i/(vals.length-1||1))*cW;
    const yOf = v=>pad.t + cH - ((v-minV)/range)*cH;
    // Grid
    ctx.strokeStyle='rgba(255,255,255,.04)';
    ctx.lineWidth=1;
    for (let i=0;i<4;i++) {
      const y=pad.t+cH*(i/3);
      ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(pad.l+cW,y); ctx.stroke();
      const gv = maxV-range*(i/3);
      ctx.fillStyle='rgba(255,255,255,.18)';
      ctx.font=`9px IBM Plex Mono`;
      ctx.textAlign='right';
      ctx.fillText('$'+f(gv,0), pad.l-6, y+3);
    }
    // Baseline
    const baseY = yOf(initBal);
    ctx.strokeStyle='rgba(255,255,255,.08)';
    ctx.setLineDash([4,4]);
    ctx.beginPath(); ctx.moveTo(pad.l,baseY); ctx.lineTo(pad.l+cW,baseY); ctx.stroke();
    ctx.setLineDash([]);
    // Fill gradient
    const lastIsUp = vals[vals.length-1] >= initBal;
    const grad = ctx.createLinearGradient(0,pad.t,0,pad.t+cH);
    if (lastIsUp) {
      grad.addColorStop(0,'rgba(14,203,129,.25)');
      grad.addColorStop(1,'rgba(14,203,129,.02)');
    } else {
      grad.addColorStop(0,'rgba(246,70,93,.18)');
      grad.addColorStop(1,'rgba(246,70,93,.02)');
    }
    ctx.beginPath();
    ctx.moveTo(xOf(0), yOf(vals[0]));
    vals.forEach((v,i)=>ctx.lineTo(xOf(i),yOf(v)));
    ctx.lineTo(xOf(vals.length-1), H-pad.b);
    ctx.lineTo(pad.l, H-pad.b);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();
    // Line
    ctx.beginPath();
    ctx.moveTo(xOf(0), yOf(vals[0]));
    vals.forEach((v,i)=>ctx.lineTo(xOf(i),yOf(v)));
    ctx.strokeStyle = lastIsUp?'var(--green)':'var(--red)';
    ctx.lineWidth=2;
    ctx.stroke();
    // Last point dot
    const lx=xOf(vals.length-1), ly=yOf(vals[vals.length-1]);
    ctx.beginPath();
    ctx.arc(lx,ly,4,0,Math.PI*2);
    ctx.fillStyle=lastIsUp?'var(--green)':'var(--red)';
    ctx.fill();
  });
}

// ══════════════════════════════════════════
// TOASTS
// ══════════════════════════════════════════
function renderToasts(toasts) {
  if (!lastData?.settings?.toast_enabled) return;
  toasts.forEach(t=>{
    if (shownToasts.has(t.ts)) return;
    shownToasts.add(t.ts);
    showToast(t.msg, t.kind||'info');
  });
}
function showToast(msg, kind='info') {
  const c = document.getElementById('toastContainer');
  const d = document.createElement('div');
  d.className = `toast ${kind}`;
  d.textContent = msg;
  c.appendChild(d);
  setTimeout(()=>{
    d.style.animation='slideOut .25s ease-in forwards';
    setTimeout(()=>d.remove(),250);
  }, 4000);
}

// ══════════════════════════════════════════
// STATE BADGE
// ══════════════════════════════════════════
function renderState(s) {
  const b = document.getElementById('stateBadge');
  const tb = document.getElementById('toggleBtn');
  const eb = document.getElementById('emerBtn');
  const rb = document.getElementById('resumeBtn');
  if (s.emergency_stop) {
    b.textContent='🚨 EMERGENCY'; b.className='state-badge state-emer';
    tb.style.display='none'; rb.style.display='inline-flex'; eb.style.display='none';
  } else if (s.calendar_paused) {
    b.textContent='📅 Paused — Event'; b.className='state-badge state-calendar';
    tb.textContent='⏸ Paused'; tb.className='btn btn-ghost';
    tb.style.display='inline-flex'; rb.style.display='none'; eb.style.display='inline-flex';
  } else if (!s.active) {
    b.textContent='⏸ PAUSED'; b.className='state-badge state-paused';
    tb.textContent='▶ Activate'; tb.className='btn btn-green';
    tb.style.display='inline-flex'; rb.style.display='none'; eb.style.display='inline-flex';
  } else {
    b.textContent='✅ ACTIVE'; b.className='state-badge state-active';
    tb.textContent='⏸ Pause'; tb.className='btn btn-yellow';
    tb.style.display='inline-flex'; rb.style.display='none'; eb.style.display='inline-flex';
  }
}

// ══════════════════════════════════════════
// SETTINGS SYNC
// ══════════════════════════════════════════
function syncSettings(s) {
  const set = (id,v)=>{ const el=document.getElementById(id); if(!el)return; el.type==='checkbox'?el.checked=!!v:el.value=v; };
  set('s-buy-mode',s.spot_buy_mode); set('s-buy-val',s.spot_buy_value);
  set('s-sell-r',s.spot_sell_ratio); set('s-max-pos',s.spot_max_positions);
  set('fut-en',s.futures_enabled);   set('f-val',s.futures_value);
  set('lev-in',s.leverage);          set('f-max-pos',s.futures_max_positions);
  set('risk-en',s.risk_enabled);     set('trail-pct',s.trailing_stop_pct);
  set('fsl-pct',s.fixed_stop_loss_pct);
  set('ps-en',s.position_sizing_enabled); set('ps-pct',s.position_sizing_pct);
  set('max-conc',s.max_concentration_pct);
  set('dl-en',s.daily_loss_enabled); set('dl-pct',s.daily_loss_limit_pct);
  set('sess-en',s.session_enabled);  set('sess-s',s.session_start); set('sess-e',s.session_end);
  set('cal-en',s.calendar_enabled);  set('cal-b',s.calendar_pause_before); set('cal-a',s.calendar_resume_after);
  set('snd-en',s.sound_enabled);     set('toast-en',s.toast_enabled);
  set('tg-en',s.telegram_enabled);   set('tg-trade',s.telegram_on_trade);
  set('tg-err',s.telegram_on_error); set('tg-rep',s.telegram_daily_report);
  set('tg-time',s.telegram_report_time);
}

// ══════════════════════════════════════════
// TRADE PAIRS
// ══════════════════════════════════════════
let allTradePairs = [];

function renderTradePairs() {
  const fm  = document.getElementById('tp-filter-market')?.value || '';
  const fs  = document.getElementById('tp-filter-status')?.value || '';
  const fp  = (document.getElementById('tp-filter-pair')?.value || '').toUpperCase();
  const fr  = document.getElementById('tp-filter-result')?.value || '';

  const filtered = allTradePairs.filter(t =>
    (!fm || t.market === fm) &&
    (!fs || t.status === fs) &&
    (!fp || t.pair.includes(fp)) &&
    (!fr || (fr === 'win' ? t.pnl > 0 : t.pnl < 0))
  );

  // Summary cards
  const opens   = allTradePairs.filter(t=>t.status==='OPEN');
  const closed  = allTradePairs.filter(t=>t.status==='CLOSED');
  const realPnl = closed.reduce((s,t)=>s+t.pnl,0);
  if (document.getElementById('tp-total'))  document.getElementById('tp-total').textContent  = allTradePairs.length;
  if (document.getElementById('tp-open'))   document.getElementById('tp-open').textContent   = opens.length;
  if (document.getElementById('tp-closed')) document.getElementById('tp-closed').textContent = closed.length;
  if (document.getElementById('tp-pnl')) {
    const el = document.getElementById('tp-pnl');
    el.textContent = (realPnl>=0?'+':'')+f(realPnl)+'$';
    el.className = 'mc-val '+(realPnl>=0?'mc-green':'mc-red');
  }

  if (document.getElementById('tp-count-info'))
    document.getElementById('tp-count-info').textContent = filtered.length+' pairs';

  const tbody = document.getElementById('tp-tbody');
  if (!tbody) return;

  if (!filtered.length) {
    tbody.innerHTML = '<tr><td colspan="14"><div class="empty-state"><span class="ei">🔗</span><span class="et">No trade pairs match filters</span></div></td></tr>';
    return;
  }

  const reasonMap2 = {stop_loss:'🛑 Stop Loss', peak_exit:'🎯 Peak', trailing_stop:'📉 Trail', '—':'—', '':'—'};
  const sideMap = {
    buy:'<span class="tb tb-buy">BUY</span>',
    long_open:'<span class="tb tb-long">LONG</span>',
    short_open:'<span class="tb tb-short">SHORT</span>',
  };

  tbody.innerHTML = filtered.map(t => {
    const isOpen   = t.status === 'OPEN';
    const isWin    = !isOpen && t.pnl > 0;
    const isLoss   = !isOpen && t.pnl < 0;
    const rowClass = isOpen ? 'tp-open-row' : isWin ? 'tp-win-row' : 'tp-loss-row';

    const statusBadge = isOpen
      ? '<span class="tp-status-open">🟢 OPEN</span>'
      : isWin
        ? '<span class="tp-status-closed-win">✅ WIN</span>'
        : '<span class="tp-status-closed-loss">❌ LOSS</span>';

    const mkt = t.market==='FUTURES'
      ? '<span class="mkt-f">F</span>'
      : '<span class="mkt-s">S</span>';

    const sellPriceHtml = isOpen
      ? `<span class="tp-live-price">${f(t.sell_price,4)}</span>`
      : `<span style="color:var(--red);font-family:var(--mono)">${f(t.sell_price,4)}</span>`;

    const sellDateHtml = isOpen
      ? '<span style="color:var(--blue);font-size:10px;font-family:var(--mono)">Live ●</span>'
      : `<div style="font-family:var(--mono);font-size:10px">${t.sell_date}</div><div style="font-size:9px;color:var(--t2);font-family:var(--mono)">${t.sell_time}</div>`;

    // Price change direction arrow
    const diff = t.sell_price - t.buy_price;
    const arrow = diff > 0
      ? '<span style="color:var(--green)">▲</span>'
      : diff < 0
        ? '<span style="color:var(--red)">▼</span>'
        : '<span style="color:var(--t3)">━</span>';

    const pnlClass = t.pnl > 0 ? 'pnl-pos' : t.pnl < 0 ? 'pnl-neg' : 'pnl-nil';
    const pnlSign  = t.pnl > 0 ? '+' : '';

    return `<tr class="${rowClass}">
      <td>${statusBadge}</td>
      <td>${mkt}</td>
      <td class="td-pair">${t.pair}</td>
      <td>${sideMap[t.side]||t.side}</td>
      <td>
        <div style="font-family:var(--mono);font-size:10px">${t.buy_date}</div>
        <div style="font-size:9px;color:var(--t2);font-family:var(--mono)">${t.buy_time}</div>
      </td>
      <td style="color:var(--green);font-family:var(--mono)">${f(t.buy_price,4)}</td>
      <td style="color:var(--gold);font-family:var(--mono)">${t.buy_total>0?f(t.buy_total,2)+'$':'—'}</td>
      <td>${sellDateHtml}</td>
      <td>${sellPriceHtml}</td>
      <td style="text-align:center">${arrow}</td>
      <td><span class="${pnlClass}" style="font-size:13px;font-weight:700">${pnlSign}${f(t.pnl,2)}$</span></td>
      <td><span class="${pnlClass}">${pnlSign}${t.pnl_pct}%</span></td>
      <td style="color:var(--t2);font-family:var(--mono);font-size:10px">${t.duration}</td>
      <td style="color:var(--t2);font-size:11px">${reasonMap2[t.reason]||t.reason||'—'}</td>
    </tr>`;
  }).join('');
}

function clearTpFilters() {
  ['tp-filter-market','tp-filter-status','tp-filter-result'].forEach(id=>{
    const el=document.getElementById(id); if(el) el.value='';
  });
  const pp=document.getElementById('tp-filter-pair'); if(pp) pp.value='';
  renderTradePairs();
}

// ══════════════════════════════════════════
// CONTROLS
// ══════════════════════════════════════════
const api = async(url,body)=>{
  const r = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  return r.json();
};
async function toggleBot()       { await api('/control/toggle') }
async function resumeBot()       { await api('/control/resume') }
async function liquidateSpot()   { if(confirm('Liquidate ALL Spot positions?'))  await api('/liquidate') }
async function liquidateFutures(){ if(confirm('Close ALL Futures positions?'))   await api('/liquidate/futures') }
async function clearErrors()     { await api('/errors/clear') }
async function ss(key,val)       { await api('/settings/update',{key,value:val}) }

async function emergencyStop() {
  if (!confirm('🚨 EMERGENCY STOP!\nThis will immediately sell ALL positions.\n\nConfirm?')) return;
  await api('/control/emergency');
}

// ══════════════════════════════════════════
// TABS
// ══════════════════════════════════════════
function switchTab(name, btn) {
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  if (btn) btn.classList.add('active');
  const p = document.getElementById('tab-'+name);
  if (p) p.classList.add('active');
}

// ══════════════════════════════════════════
// PERIOD
// ══════════════════════════════════════════
function setPeriod(h, el) {
  document.querySelectorAll('.period-tab').forEach(t=>t.classList.remove('active'));
  el.classList.add('active');
  ss('report_hours', h);
}

// ══════════════════════════════════════════
// FILTERS
// ══════════════════════════════════════════
function filterTrades() { if (allTrades.length) renderTrades(allTrades); }
function clearFilters() {
  document.getElementById('filter-market').value='';
  document.getElementById('filter-type').value='';
  document.getElementById('filter-pair').value='';
  filterTrades();
}

// ══════════════════════════════════════════
// MOVERS
// ══════════════════════════════════════════
async function loadMovers() {
  document.getElementById('movers-grid').innerHTML='<div class="empty-state" style="grid-column:1/-1"><span class="ei" style="opacity:.4">⏳</span><span class="et">Loading...</span></div>';
  const data = await fetch('/movers').then(r=>r.json()).catch(()=>[]);
  if (!data.length) {
    document.getElementById('movers-grid').innerHTML='<div class="empty-state" style="grid-column:1/-1"><span class="ei">⚠️</span><span class="et">No data available</span></div>';
    return;
  }
  document.getElementById('movers-grid').innerHTML = data.map(m=>`
    <div class="mover-card">
      <div class="mover-sym">${m.symbol}</div>
      <div class="mover-pct" style="color:${m.change_pct>=0?'var(--green)':'var(--red)'}">${m.change_pct>=0?'+':''}${m.change_pct}%</div>
      <div class="mover-info">${f(m.price,4)} USDT</div>
      <div class="mover-info">${m.volume_m}M Vol</div>
    </div>`).join('');
}

// ══════════════════════════════════════════
// EXCEL EXPORT
// ══════════════════════════════════════════
function openModal(id) { document.getElementById(id).classList.add('open') }
function closeModal(id){ document.getElementById(id).classList.remove('open') }

function doExport() {
  if (!lastData?.trades?.length) { alert('No trades to export'); return; }
  const st = lastData.stats || {};
  const rows = lastData.trades.map(t=>({
    'Date':          t.date||'',
    'Time':          t.time||'',
    'Market':        t.market||'',
    'Pair':          t.pair||'',
    'Type':          t.act||'',
    'Quantity':      t.amount||0,
    'Price':         t.price||0,
    'Total ($)':     t.total||0,
    'PnL ($)':       t.pnl||0,
    'Reason':        t.reason||'',
    'Status':        t.success?'Success':'Failed',
    'Error':         t.err||'',
  }));
  // Add summary sheet
  const summary = [
    {'Metric':'Total Trades',       'Value':st.total||0},
    {'Metric':'Wins',               'Value':st.wins||0},
    {'Metric':'Losses',             'Value':st.losses||0},
    {'Metric':'Win Rate',           'Value':(st.win_rate||0)+'%'},
    {'Metric':'Net PnL ($)',        'Value':st.total_pnl||0},
    {'Metric':'Profit Factor',      'Value':st.profit_factor||0},
    {'Metric':'Sharpe Ratio',       'Value':st.sharpe||0},
    {'Metric':'Max Drawdown ($)',   'Value':st.max_drawdown||0},
    {'Metric':'Best Trade ($)',     'Value':st.best_trade||0},
    {'Metric':'Worst Trade ($)',    'Value':st.worst_trade||0},
    {'Metric':'Avg Win ($)',        'Value':st.avg_win||0},
    {'Metric':'Avg Loss ($)',       'Value':st.avg_loss||0},
    {'Metric':'Expectancy ($)',     'Value':st.expectancy||0},
    {'Metric':'Consecutive Wins',   'Value':st.consecutive_wins||0},
    {'Metric':'Consecutive Losses', 'Value':st.consecutive_losses||0},
    {'Metric':'Export Date',        'Value':new Date().toLocaleString()},
  ];
  const ws1 = XLSX.utils.json_to_sheet(rows);
  const ws2 = XLSX.utils.json_to_sheet(summary);
  ws1['!cols'] = [{wch:12},{wch:10},{wch:8},{wch:14},{wch:12},{wch:10},{wch:12},{wch:10},{wch:10},{wch:14},{wch:8},{wch:30}];
  ws2['!cols'] = [{wch:22},{wch:16}];
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb,'Trades',ws1);
  XLSX.utils.book_append_sheet(wb,'Summary',ws2);
  const d = new Date().toLocaleDateString('en-GB').replace(/\//g,'-');
  XLSX.writeFile(wb,`SOVEREIGN_V8_${d}.xlsx`);
  closeModal('excelModal');
}

// ══════════════════════════════════════════
// CLOCK
// ══════════════════════════════════════════
setInterval(()=>{
  const el = document.getElementById('clock');
  if (el) el.textContent = new Date().toLocaleTimeString('en-US',{hour12:false});
},1000);

// AI AGENTS + OPTIMIZER
const AGENTS_URL = 'https://sovereign-agents.onrender.com';

async function loadAgents() {
  try {
    document.getElementById('agents-updated').textContent = 'Loading...';
    const [agData, optData] = await Promise.all([
      fetch(AGENTS_URL + '/api/agents').then(r=>r.json()).catch(()=>null),
      fetch(AGENTS_URL + '/api/optimizer').then(r=>r.json()).catch(()=>null),
    ]);
    if (agData)  renderAgentHealth(agData);
    if (agData)  renderMarketSignals(agData);
    if (agData)  renderRisk(agData);
    if (agData)  renderEvents(agData);
    if (optData) renderOptimizerResults(optData);
    document.getElementById('agents-updated').textContent = 'Updated: ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('agents-updated').textContent = 'Error: ' + e.message;
  }
}

function renderAgentHealth(data) {
  const health = data.health || {};
  const names = {
    execution_quality:   {icon:'⚡', label:'Execution'},
    market_intelligence: {icon:'📊', label:'Market Intel'},
    risk_management:     {icon:'🛡️', label:'Risk Mgmt'},
    audit_backtesting:   {icon:'📋', label:'Audit'},
    meta_supervisor:     {icon:'🧠', label:'Meta Super'},
    orchestrator:        {icon:'🎯', label:'Orchestrator'},
  };
  document.getElementById('agent-health-grid').innerHTML =
    Object.entries(names).map(([k, info]) => {
      const h  = health[k] || {};
      const ok = h.healthy;
      const ago = h.seconds_ago ? Math.round(h.seconds_ago)+'s' : '--';
      return `<div class="metric-card" style="border-top:2px solid ${ok?'var(--green)':'var(--red)'}">
        <div class="mc-icon">${info.icon}</div>
        <div class="mc-lbl">${info.label}</div>
        <div class="mc-val" style="font-size:14px;color:${ok?'var(--green)':'var(--red)'}">${ok?'✅ ON':'❌ OFF'}</div>
        <div class="mc-sub">${ago} ago</div>
      </div>`;
    }).join('');
}

function renderOptimizerResults(data) {
  const status  = data.status  || {};
  const results = data.results || {};
  const card = document.getElementById('optimizer-status-card');
  if (status.running) {
    card.style.display = '';
    const pct = status.progress || 0;
    document.getElementById('opt-progress').textContent = pct + '%';
    document.getElementById('opt-bar').style.width      = pct + '%';
    document.getElementById('opt-symbol').textContent   = 'Analyzing: ' + (status.current_symbol || '...');
  } else {
    card.style.display = 'none';
  }
  if (status.last_run) {
    document.getElementById('opt-last-run').textContent =
      'Last: ' + new Date(status.last_run * 1000).toLocaleString();
  }
  const body = document.getElementById('opt-results-body');
  const keys = Object.keys(results);
  if (!keys.length) {
    body.innerHTML = '<div class="empty-state"><span class="ei">⚙️</span><span class="et">Optimizer runs every 24h — results appear here</span></div>';
    return;
  }
  body.innerHTML = keys.map(sym => {
    const r   = results[sym];
    const imp = r.improvement || 0;
    const op  = r.old_perf   || {};
    const np  = r.new_perf   || {};
    const ch  = r.changes    || [];
    const coin = sym.replace('USDT','');
    const impColor = imp > 10 ? 'var(--green)' : imp > 0 ? 'var(--gold)' : 'var(--red)';
    const changed   = ch.filter(c => c.changed);
    const unchanged = ch.filter(c => !c.changed);
    return `<div style="border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:14px;background:var(--bg2)">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <span style="font-family:var(--mono);font-weight:700;font-size:16px">${coin}/USDT</span>
        <div style="display:flex;gap:8px;align-items:center">
          <span style="font-family:var(--mono);font-size:13px;font-weight:700;color:${impColor}">${imp>0?'+':''}${imp}%</span>
          ${r.applied ? '<span class="card-badge badge-green">✅ Applied</span>' : '<span class="card-badge badge-gold">📋 Review</span>'}
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:14px">
        <div style="background:var(--bg1);border-radius:8px;padding:10px">
          <div style="font-size:9px;color:var(--t3);font-family:var(--mono);margin-bottom:6px">BEFORE</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;text-align:center">
            <div><div style="font-size:9px;color:var(--t2)">Win Rate</div><div style="font-family:var(--mono);font-size:13px">${op.win_rate||0}%</div></div>
            <div><div style="font-size:9px;color:var(--t2)">PF</div><div style="font-family:var(--mono);font-size:13px">${op.profit_factor||0}</div></div>
            <div><div style="font-size:9px;color:var(--t2)">Max DD</div><div style="font-family:var(--mono);font-size:13px;color:var(--red)">${op.max_drawdown||0}%</div></div>
            <div><div style="font-size:9px;color:var(--t2)">Signals</div><div style="font-family:var(--mono);font-size:13px;color:var(--t2)">${op.total_signals||0}</div></div>
          </div>
        </div>
        <div style="background:var(--bg1);border-radius:8px;padding:10px;border:1px solid var(--green-br)">
          <div style="font-size:9px;color:var(--green);font-family:var(--mono);margin-bottom:6px">AFTER ✨</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;text-align:center">
            <div><div style="font-size:9px;color:var(--t2)">Win Rate</div><div style="font-family:var(--mono);font-size:13px;color:var(--green)">${np.win_rate||0}%</div></div>
            <div><div style="font-size:9px;color:var(--green);font-size:9px">PF</div><div style="font-family:var(--mono);font-size:13px;color:var(--green)">${np.profit_factor||0}</div></div>
            <div><div style="font-size:9px;color:var(--t2)">Max DD</div><div style="font-family:var(--mono);font-size:13px;color:var(--orange)">${np.max_drawdown||0}%</div></div>
            <div><div style="font-size:9px;color:var(--t2)">Signals</div><div style="font-family:var(--mono);font-size:13px;color:var(--t2)">${np.total_signals||0}</div></div>
          </div>
        </div>
      </div>
      ${changed.length ? `
      <div style="margin-bottom:10px">
        <div style="font-size:9px;color:var(--gold);font-family:var(--mono);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">🔄 التعديلات المقترحة</div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:6px">
          ${changed.map(c => `<div style="background:rgba(240,185,11,.06);border:1px solid var(--gold-br);border-radius:6px;padding:8px 10px">
            <div style="font-size:9px;color:var(--t2);margin-bottom:3px">${c.label}</div>
            <div style="font-family:var(--mono);font-size:12px">
              <span style="color:var(--red);text-decoration:line-through">${c.old}</span>
              <span style="color:var(--t3);margin:0 4px">→</span>
              <span style="color:var(--green);font-weight:700">${c.new}</span>
            </div>
          </div>`).join('')}
        </div>
      </div>` : ''}
      <details>
        <summary style="font-size:10px;color:var(--t3);cursor:pointer;font-family:var(--mono)">Unchanged (${unchanged.length})</summary>
        <div style="display:flex;flex-wrap:wrap;gap:5px;margin-top:8px">
          ${unchanged.map(c => `<span style="background:var(--bg1);border:1px solid var(--border);border-radius:4px;padding:3px 8px;font-family:var(--mono);font-size:10px;color:var(--t2)">${c.label}: ${c.old}</span>`).join('')}
        </div>
      </details>
    </div>`;
  }).join('');
}

function renderMarketSignals(data) {
  const signals = data.metrics?.market_intelligence?.strategy_signals || {};
  const market  = data.metrics?.dashboard_snapshot?.market || {};
  const body    = document.getElementById('ag-signals-body');
  const keys    = Object.keys(signals);
  const regimes = {trending_up:'🟢 Up', trending_down:'🔴 Down', ranging:'↔️ Range', volatile:'⚠️ Vol'};
  document.getElementById('ag-market-regime').textContent =
    Object.values(market).map(m => regimes[m.regime] || m.regime).join(' | ') || '--';
  if (!keys.length) {
    body.innerHTML = '<div class="empty-state"><span class="ei">📡</span><span class="et">No signals</span></div>';
    return;
  }
  body.innerHTML = keys.map(sym => {
    const s = signals[sym]; const m = market[sym] || {};
    const stUp = s.supertrend?.includes('صاعد');
    const sqFire = s.squeeze?.includes('انطلق');
    const htfOk = s.htf?.includes('✅');
    const allOk = stUp && sqFire && htfOk && s.mfi > 50;
    const coin = sym.replace('USDT','');
    return `<div style="padding:12px 0;border-bottom:1px solid var(--border2)">
      <div style="display:flex;justify-content:space-between;margin-bottom:8px">
        <span style="font-family:var(--mono);font-weight:700">${coin}/USDT</span>
        ${allOk ? '<span class="card-badge badge-green">🔥 SIGNAL</span>' : '<span style="font-size:10px;color:var(--t2)">'+(regimes[m.regime]||'--')+'</span>'}
      </div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:4px">
        <div style="background:var(--bg2);border-radius:5px;padding:5px;text-align:center">
          <div style="font-size:8px;color:var(--t3);margin-bottom:2px">ST</div>
          <div style="font-size:13px">${stUp ? '🟢' : '🔴'}</div>
        </div>
        <div style="background:var(--bg2);border-radius:5px;padding:5px;text-align:center">
          <div style="font-size:8px;color:var(--t3);margin-bottom:2px">SQ</div>
          <div style="font-size:13px">${sqFire ? '🔥' : '🔒'}</div>
        </div>
        <div style="background:var(--bg2);border-radius:5px;padding:5px;text-align:center">
          <div style="font-size:8px;color:var(--t3);margin-bottom:2px">MFI</div>
          <div style="font-family:var(--mono);font-size:11px;color:${s.mfi>70?'var(--red)':s.mfi>50?'var(--green)':'var(--t2)'}">${(s.mfi||0).toFixed(0)}</div>
        </div>
        <div style="background:var(--bg2);border-radius:5px;padding:5px;text-align:center">
          <div style="font-size:8px;color:var(--t3);margin-bottom:2px">HTF</div>
          <div style="font-size:13px">${htfOk ? '✅' : '❌'}</div>
        </div>
      </div>
    </div>`;
  }).join('');
}

function renderRisk(data) {
  const rm   = data.metrics?.risk_management || {};
  const risk = data.metrics?.dashboard_snapshot?.risk || {};
  const meta = data.metrics?.meta_supervisor || {};
  const sc   = rm.risk_score || 0;
  const col  = sc > 70 ? 'var(--red)' : sc > 40 ? 'var(--orange)' : 'var(--green)';
  document.getElementById('ag-risk-badge').textContent = 'Risk: ' + sc + '/100';
  document.getElementById('ag-risk-badge').className   = 'card-badge ' + (sc>70?'badge-red':sc>40?'badge-gold':'badge-green');
  document.getElementById('ag-risk-body').innerHTML = `
    <div class="stat-row"><span class="stat-lbl">System Health</span><span class="stat-val" style="color:${col}">${(meta.system_health_pct||0).toFixed(0)}%</span></div>
    <div class="stat-row"><span class="stat-lbl">Risk Score</span><span class="stat-val" style="color:${col}">${sc}/100</span></div>
    <div class="stat-row"><span class="stat-lbl">VaR 95%</span><span class="stat-val mc-red">${(rm.var_95||0).toFixed(2)}%</span></div>
    <div class="stat-row"><span class="stat-lbl">Drawdown</span><span class="stat-val mc-red">${(rm.current_drawdown_pct||0).toFixed(2)}%</span></div>
    <div class="stat-row"><span class="stat-lbl">Trading</span><span class="stat-val" style="color:${risk.trading_halted?'var(--red)':'var(--green)'}">${risk.trading_halted?'🚨 HALTED':'✅ ACTIVE'}</span></div>
    <div class="stat-row"><span class="stat-lbl">Breaches</span><span class="stat-val">${rm.breaches_today||0}</span></div>`;
}

function renderEvents(data) {
  const evs = data.metrics?.dashboard_snapshot?.recent_events || [];
  const pc  = {3:'var(--red)', 2:'var(--orange)', 1:'var(--t2)'};
  const pl  = {3:'🔴 HIGH', 2:'🟡 MED', 1:'⚪ LOW'};
  const al  = {meta_supervisor:'🧠', risk_management:'🛡️', market_intelligence:'📊', orchestrator:'🎯', audit_backtesting:'📋', execution_quality:'⚡'};
  const tl  = {agent_down:'Agent Down', var_update:'VaR', risk_breach:'Risk Breach', audit_log:'Audit', strategy_signal:'Signal'};
  document.getElementById('ag-events-count').textContent = evs.length;
  if (!evs.length) {
    document.getElementById('ag-events-tbody').innerHTML =
      '<tr><td colspan="5"><div class="empty-state"><span class="ei">📡</span><span class="et">No events</span></div></td></tr>';
    return;
  }
  document.getElementById('ag-events-tbody').innerHTML = evs.map(ev => {
    const ts  = ev.timestamp ? new Date(ev.timestamp*1000).toLocaleTimeString() : '--';
    const msg = ev.payload?.message || ev.type || '--';
    return `<tr>
      <td class="td-muted">${ts}</td>
      <td style="font-family:var(--mono);font-size:12px">${al[ev.source]||''} ${ev.source||''}</td>
      <td><span class="card-badge badge-blue" style="font-size:9px">${tl[ev.type]||ev.type}</span></td>
      <td style="font-family:var(--mono);font-size:11px;max-width:280px;white-space:normal">${msg}</td>
      <td style="font-family:var(--mono);font-size:10px;color:${pc[ev.priority]||'var(--t2)'}">${pl[ev.priority]||'--'}</td>
    </tr>`;
  }).join('');
}

setInterval(() => {
  if (document.getElementById('tab-agents')?.classList.contains('active')) loadAgents();
}, 60000);

// ══════════════════════════════════════════
// RESIZE: redraw charts
// ══════════════════════════════════════════
window.addEventListener('resize', ()=>{
  if (lastData) renderEquity(lastData.equity_curve||[], lastData.initial_balance||10000);
});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT",8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
