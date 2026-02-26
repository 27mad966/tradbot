import os
import ccxt
import asyncio
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

class HardTestBot:
    def __init__(self):
        # ضع مفاتيحك هنا مباشرة للتجربة النهائية
        self.api_key = "XnEm0wn9uAFLpwFAXZZ3UhkFAWiYgWU5h5fIRnucvVoylC6BfPEabdKDJ9u8NX5Q" 
        self.secret_key = "YFOf0OwhIpHIlDiaPDGfkLCHypLYEk9uHAt0AMcE7VQ4Kcy065oKQj8eSMjc4CIH"

        self.exchange = ccxt.binance({
            'apiKey': self.api_key.strip(),
            'secret': self.secret_key.strip(),
            'enableRateLimit': True,
            'options': {'adjustForTimeDifference': True}
        })
        # إجبار الاتصال برابط التست نت الظاهر في صورك السابقة
        self.exchange.urls['api']['public'] = 'https://testnet.binance.vision/api'
        self.exchange.urls['api']['private'] = 'https://testnet.binance.vision/api'

    async def get_real_status(self):
        try:
            # محاولة جلب الحساب
            bal = self.exchange.fetch_balance()
            assets = {k: v for k, v in bal['total'].items() if v > 0}
            if assets:
                return f"✅ نجاح باهر! الرصيد المكتشف هو: {assets}"
            else:
                return "✅ تم الاتصال بنجاح، لكن الحساب صفر (USDT 0). تحتاج لشحن الحساب."
        except Exception as e:
            return f"❌ لا تزال بايننس ترفض! السبب الحقيقي: {str(e)}"

bot = HardTestBot()

@app.get("/", response_class=HTMLResponse)
async def home():
    result = await bot.get_real_status()
    return f"""
    <body style="background:#0b0e11; color:white; font-family:sans-serif; padding:50px; text-align:center;">
        <h1 style="color:#f0b90b;">اختبار الاتصال المباشر</h1>
        <div style="font-size:1.5em; border:2px solid #f0b90b; padding:30px; border-radius:20px; display:inline-block;">
            {result}
        </div>
        <p style="margin-top:20px; color:#888;">إذا ظهر "نجاح"، فالمشكلة في إعدادات Environment في ريندر.</p>
    </body>
    """

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
