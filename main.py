import os
import ccxt
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

class GlobalKeyScanner:
    def __init__(self):
        # ضع مفاتيحك هنا مباشرة للمرة الأخيرة
        self.api_key = "XnEm0wn9uAFLpwFAXZZ3UhkFAWiYgWU5h5fIRnucvVoylC6BfPEabdKDJ9u8NX5Q"
        self.secret_key = "YFOf0OwhIpHIlDiaPDGfkLCHypLYEk9uHAt0AMcE7VQ4Kcy065oKQj8eSMjc4CIH"

    def scan(self):
        # القائمة الرسمية لجميع نقاط الاتصال التجريبية
        endpoints = [
            {"name": "Spot Testnet (Vision)", "url": "https://testnet.binance.vision/api", "type": "spot"},
            {"name": "Binance Futures Testnet", "url": "https://testnet.binancefuture.com", "type": "future"},
            {"name": "Binance Sandbox Mode", "url": "https://api.binance.com", "sandbox": True}
        ]
        
        results = []
        for ep in endpoints:
            try:
                exchange = ccxt.binance({
                    'apiKey': self.api_key.strip(),
                    'secret': self.secret_key.strip(),
                    'enableRateLimit': True,
                    'options': {'adjustForTimeDifference': True}
                })
                
                if ep.get("sandbox"):
                    exchange.set_sandbox_mode(True)
                else:
                    exchange.urls['api']['public'] = ep['url']
                    exchange.urls['api']['private'] = ep['url']
                
                bal = exchange.fetch_balance()
                results.append(f"✅ {ep['name']}: نجح الاتصال! الرصيد: {bal['total'].get('USDT', 0)} USDT")
                break # إذا نجح واحد نتوقف
            except Exception as e:
                results.append(f"❌ {ep['name']}: مرفوض ({str(e)[:40]}...)")
        
        return results

bot = GlobalKeyScanner()

@app.get("/", response_class=HTMLResponse)
async def root():
    reports = bot.scan()
    content = "".join([f"<li style='margin-bottom:15px;'>{r}</li>" for r in reports])
    return f"""
    <body style="background:#0b0e11; color:white; font-family:sans-serif; padding:50px;">
        <h1 style="color:#f0b90b;">🔍 فحث هوية المفاتيح</h1>
        <ul style="font-size:1.2em; border:1px solid #333; padding:20px; border-radius:15px;">
            {content}
        </ul>
    </body>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
