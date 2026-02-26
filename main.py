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

# قائمة لتخزين WebSocket connections المفتوحة
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
        self.trades = deque(maxlen=50)

    async def get_stats(self):
        try:
            bal = self.ex.fetch_balance()
            total = bal['total'].get('USDT', 0.0)
            for c in ['BTC', 'ETH', 'SOL', 'BNB']:
                amt = bal['total'].get(c, 0.0)
                if amt > 0.0001:
                    ticker = self.ex.fetch_ticker(f"{c}/USDT")
                    total += amt * ticker['last']
            pnl = total - INITIAL_BALANCE
            return round(total, 2), round(pnl, 2), round((pnl / INITIAL_BALANCE) * 100, 2)
        except Exception as e:
            print(f"⚠️ خطأ في جلب الرصيد: {e}")
            return 10000.0, 0.0, 0.0

    def fix_pair(self, pair: str) -> str:
        pair = pair.upper().strip()
        # إصلاح تكرار USDT مثل BTCUSDTUSDT
        pair = pair.replace("USDTUSDT", "USDT")
        if "/" in pair:
            return pair
        if pair.endswith("USDT"):
            base = pair[:-4]
            return f"{base}/USDT"
        return f"{pair}/USDT"

    def execute(self, pair: str, side: str) -> dict:
        side = side.lower().strip()
        pair = self.fix_pair(pair)

        print(f"📡 إشارة واردة: {side} | {pair}")

        try:
            self.ex.load_markets()
            ticker = self.ex.fetch_ticker(pair)
            price = ticker['last']

            if "buy" in side or "long" in side:
                bal = self.ex.fetch_balance()
                usdt = bal['total'].get('USDT', 0.0)
                if settings["buy_mode"] == "fixed":
                    val = settings["buy_value"]
                else:
                    val = usdt * (settings["buy_value"] / 100)
                if val < 11:
                    val = 11
                amt = self.ex.amount_to_precision(pair, val / price)
                order = self.ex.create_market_buy_order(pair, float(amt))
                msg = f"✅ شراء {amt} @ {price}"

            elif "sell" in side or "short" in side:
                coin = pair.split('/')[0]
                bal = self.ex.fetch_balance()
                c_bal = bal['total'].get(coin, 0.0)
                if c_bal <= 0:
                    raise Exception(f"لا يوجد رصيد من {coin}")
                if settings["sell_mode"] == "percent":
                    sell_ratio = settings["sell_value"]  # 1.0 = 100%
                else:
                    sell_ratio = 1.0
                amt = self.ex.amount_to_precision(pair, c_bal * sell_ratio)
                order = self.ex.create_market_sell_order(pair, float(amt))
                msg = f"✅ بيع {amt} @ {price}"

            else:
                raise Exception(f"اتجاه غير معروف: {side}")

            res = {
                'time': datetime.now().strftime("%H:%M:%S"),
                'pair': pair,
                'act': side,
                'price': price,
                'st': msg
            }
            self.trades.appendleft(res)
            print(f"💰 نجاح: {msg}")
            return res

        except Exception as e:
            err = str(e)
            print(f"❌ فشل: {err}")
            res = {
                'time': datetime.now().strftime("%H:%M:%S"),
                'pair': pair,
                'act': side,
                'price': 0,
                'st': f"❌ {err[:60]}"
            }
            self.trades.appendleft(res)
            return res

    def liquidate_all(self):
        """بيع جميع العملات المتاحة"""
        try:
            bal = self.ex.fetch_balance()
            for coin, amt in bal['total'].items():
                if coin == 'USDT' or amt < 0.0001:
                    continue
                pair = f"{coin}/USDT"
                try:
                    self.ex.load_markets()
                    if pair in self.ex.markets:
                        order = self.ex.create_market_sell_order(pair, amt)
                        print(f"🔴 تصفية: بيع {amt} {coin}")
                except Exception as e:
                    print(f"⚠️ فشل تصفية {coin}: {e}")
        except Exception as e:
            print(f"❌ خطأ في التصفية: {e}")


bot = TradingBot()


async def broadcast(data: dict):
    """إرسال بيانات لجميع المتصلين فوراً"""
    disconnected = []
    for ws in active_connections:
        try:
            await ws.send_json(data)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        active_connections.remove(ws)


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SOVEREIGN V4.8</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-[#0b0e11] text-white p-6 font-sans">
        <div class="max-w-4xl mx-auto">
            <div class="flex justify-between items-center bg-white/5 p-6 rounded-2xl mb-6">
                <h1 class="text-yellow-500 font-black italic text-xl">SOVEREIGN V4.8</h1>
                <div class="text-sm">
                    <span class="text-gray-400">الرصيد: </span>
                    <span id="balance" class="text-emerald-400 font-bold">--</span>
                    <span class="text-gray-400"> USDT</span>
                </div>
                <div id="status" class="text-xs text-yellow-400">⏳ جاري الاتصال...</div>
            </div>

            <div class="bg-white/5 rounded-2xl overflow-hidden">
                <table class="w-full text-right text-sm">
                    <thead class="bg-white/10 text-gray-400">
                        <tr>
                            <th class="p-4">الوقت</th>
                            <th class="p-4">الزوج</th>
                            <th class="p-4">النوع</th>
                            <th class="p-4">السعر</th>
                            <th class="p-4">الحالة</th>
                        </tr>
                    </thead>
                    <tbody id="trades" class="divide-y divide-gray-800">
                        <tr><td colspan="5" class="p-8 text-center text-gray-500">في انتظار الإشارات...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>

        <script>
            let reconnectDelay = 2000;

            function connect() {
                const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
                const ws = new WebSocket(proto + '//' + location.host + '/ws');

                ws.onopen = () => {
                    document.getElementById('status').textContent = '🟢 متصل';
                    document.getElementById('status').className = 'text-xs text-emerald-400';
                    reconnectDelay = 2000;
                };

                ws.onmessage = (e) => {
                    const d = JSON.parse(e.data);
                    document.getElementById('balance').textContent = d.balance.toLocaleString();
                    
                    const tbody = document.getElementById('trades');
                    if (d.trades.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="5" class="p-8 text-center text-gray-500">في انتظار الإشارات...</td></tr>';
                        return;
                    }
                    tbody.innerHTML = d.trades.map(x => `
                        <tr class="hover:bg-white/5 transition">
                            <td class="p-4 text-gray-500">${x.time}</td>
                            <td class="p-4 font-bold">${x.pair}</td>
                            <td class="p-4 uppercase font-bold ${x.act.includes('buy') || x.act.includes('long') ? 'text-emerald-400' : 'text-red-400'}">${x.act}</td>
                            <td class="p-4 text-yellow-500">${x.price > 0 ? x.price.toLocaleString() : '--'}</td>
                            <td class="p-4 text-xs font-bold text-gray-300">${x.st}</td>
                        </tr>
                    `).join('');
                };

                ws.onclose = () => {
                    document.getElementById('status').textContent = '🔴 انقطع الاتصال، إعادة المحاولة...';
                    document.getElementById('status').className = 'text-xs text-red-400';
                    setTimeout(connect, reconnectDelay);
                    reconnectDelay = Math.min(reconnectDelay * 1.5, 30000);
                };

                ws.onerror = () => ws.close();
            }

            connect();
        </script>
    </body>
    </html>
    """


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    active_connections.append(ws)
    print(f"🔌 متصل جديد | إجمالي: {len(active_connections)}")
    try:
        # أرسل البيانات الحالية فوراً عند الاتصال
        t, p, n = await bot.get_stats()
        await ws.send_json({"balance": t, "trades": list(bot.trades)})
        # ثم استمر في الإرسال كل 5 ثواني
        while True:
            await asyncio.sleep(5)
            t, p, n = await bot.get_stats()
            await ws.send_json({"balance": t, "trades": list(bot.trades)})
    except Exception:
        pass
    finally:
        if ws in active_connections:
            active_connections.remove(ws)
        print(f"🔌 انقطع اتصال | إجمالي: {len(active_connections)}")


@app.post("/webhook")
async def webhook(s: Signal):
    if not settings.get("active", True):
        return {"status": "inactive", "msg": "البوت متوقف"}
    
    result = bot.execute(s.pair, s.direction)
    
    # أبلغ جميع المتصلين فوراً بعد تنفيذ الإشارة
    t, p, n = await bot.get_stats()
    await broadcast({"balance": t, "trades": list(bot.trades)})
    
    return result


@app.post("/liquidate")
async def liquidate():
    bot.liquidate_all()
    t, p, n = await bot.get_stats()
    await broadcast({"balance": t, "trades": list(bot.trades)})
    return {"ok": True, "msg": "تم تصفية جميع المراكز"}


@app.get("/health")
async def health():
    return {"status": "ok", "trades_count": len(bot.trades)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
