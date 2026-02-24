import os
from fastapi import FastAPI, Form, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import ccxt
import uvicorn

DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "AHMED_BOSS_2026")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "SNIPER_V96_SECRET")

# قراءة المفاتيح من Environment Variables
BINANCE_TESTNET_API_KEY = "8IRAIkU2bKuFd5ib8iRDbKGEz2aXUyf67DTlyXfu1J9OxuPV1CiY2H9ImmOcGwiY"
BINANCE_TESTNET_SECRET_KEY = "daWtLcs2aVjG2zsVCRLsRti6zN0AmDbSvo3V8DCVzenUcfWnKb7s774CfJmCJm6o"

def create_binance_client():
    if not BINANCE_TESTNET_API_KEY or not BINANCE_TESTNET_SECRET_KEY:
        raise RuntimeError("BINANCE_TESTNET_API_KEY و BINANCE_TESTNET_SECRET_KEY مطلوبة")
    
    exchange = ccxt.binance({
        "apiKey": BINANCE_TESTNET_API_KEY,
        "secret": BINANCE_TESTNET_SECRET_KEY,
        "enableRateLimit": True,
        "options": {
            "adjustForTimeDifference": True,
            "recvWindow": 60000,
            "defaultType": "spot",
        },
    })
    exchange.set_sandbox_mode(True)
    return exchange

try:
    exchange = create_binance_client()
    exchange_init_error = None
except Exception as e:
    exchange = None
    exchange_init_error = str(e)

app = FastAPI()

class Signal(BaseModel):
    passphrase: str
    symbol: str
    side: str

@app.get("/", response_class=HTMLResponse)
async def login_page():
    return """
    <body style="background:#0d1117;color:white;display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;">
        <form action="/auth" method="post" style="background:#161b22;padding:40px;border-radius:12px;border:1px solid #30363d;text-align:center;">
            <h2>Sovereign Station</h2>
            <input type="password" name="password" placeholder="Key" style="padding:12px;width:250px;border-radius:6px;border:none;margin-bottom:20px;background:#0d1117;color:white;border:1px solid #30363d;"><br>
            <button type="submit" style="padding:12px 40px;background:#238636;color:white;border:none;border-radius:6px;cursor:pointer;">LOGIN</button>
        </form>
    </body>
    """

@app.post("/auth")
async def auth(password: str = Form(...)):
    if password == DASHBOARD_PASS:
        response = RedirectResponse(url="/dashboard", status_code=303)
        response.set_cookie(key="auth_token", value=DASHBOARD_PASS, httponly=True)
        return response
    return RedirectResponse(url="/")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(auth_token: str = Cookie(None)):
    if auth_token != DASHBOARD_PASS:
        return RedirectResponse(url="/")

    if exchange is None:
        display = f"❌ خطأ الاتصال: {exchange_init_error}"
    else:
        try:
            balance = exchange.fetch_balance()
            active = {
                k: float(v["total"])
                for k, v in balance.items()
                if isinstance(v, dict) and float(v.get("total", 0)) > 0
            }
            top_assets = dict(list(active.items())[:10])  # أفضل 10 أصول
            display = f"✅ {len(active)} أصل | أهم 10: {top_assets}"
        except Exception as e:
            display = f"❌ خطأ في جلب الرصيد: {str(e)}"

    return f"""
    <body style="background:#0d1117;color:white;padding:50px;font-family:sans-serif;">
        <h1>🚀 Sovereign Station Dashboard</h1>
        <div style="background:#161b22;padding:30px;border-radius:12px;border:1px solid #30363d;margin:20px 0;">
            <h2>📊 الحالة: <span style="color:#238636;">TESTNET</span></h2>
            <h2>💰 الأصول: <span style="color:#58a6ff;">{display}</span></h2>
        </div>
    </body>
    """

@app.post("/webhook")
async def handle_webhook(signal: Signal):
    if signal.passphrase != WEBHOOK_SECRET:
        return {"status": "error"}
    return {"status": "success"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
