import os
import ccxt
import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse

app = FastAPI()

class DiagnosticBot:
    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY", "").strip()
        self.secret_key = os.getenv("BINANCE_SECRET_KEY", "").strip()
        
        self.exchange = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.secret_key,
            'enableRateLimit': True,
            'options': {'adjustForTimeDifference': True, 'defaultType': 'spot'}
        })
        self.exchange.urls['api']['public'] = 'https://testnet.binance.vision/api'
        self.exchange.urls['api']['private'] = 'https://testnet.binance.vision/api'

    async def check_everything(self):
        results = []
        try:
            # 1. فحص الاتصال الأساسي
            results.append("🔍 فحص الاتصال: جاري الاتصال بـ Binance Testnet...")
            
            # 2. جلب الحساب كاملاً (Raw Data)
            account_info = self.exchange.fetch_balance()
            
            # 3. تصفية الأرصدة التي تزيد عن صفر
            balances = {k: v for k, v in account_info['total'].items() if v > 0}
            
            if balances:
                results.append(f"✅ تم العثور على أرصدة: {balances}")
            else:
                results.append("⚠️ الحساب متصل، لكن جميع الأرصدة صفر (0.0).")
                results.append("💡 نصيحة: الحساب يحتاج شحن من الـ Faucet في موقع بايننس.")
                
        except Exception as e:
            results.append(f"❌ خطأ تقني دقيق: {str(e)}")
            if "API-key format" in str(e):
                results.append("📝 التشخيص: بايننس تقول أن شكل المفتاح غير صحيح (تأكد من عدم وجود مسافات).")
            elif "Signature for this request is not valid" in str(e):
                results.append("📝 التشخيص: السر (Secret Key) غير متوافق مع المفتاح (API Key).")
            elif "Timestamp for this request" in str(e):
                results.append("📝 التشخيص: مشكلة توقيت بين سيرفر ريندر وبايننس.")
        
        return results

diag_bot = DiagnosticBot()

@app.get("/", response_class=HTMLResponse)
async def diagnostic_page():
    res = await diag_bot.check_everything()
    html_content = "".join([f"<li style='margin-bottom:10px;'>{line}</li>" for line in res])
    return f"""
    <html dir="rtl">
    <body style="background:#0b0e11; color:white; font-family:sans-serif; padding:50px;">
        <h1 style="color:#f0b90b;">تقرير فحص الحساب الحقيقي</h1>
        <ul style="font-size:1.2em; list-style:none; border:1px solid #333; padding:20px; border-radius:10px;">
            {html_content}
        </ul>
        <p style="margin-top:20px; color:#888;">إذا رأيت أرصدة بالأعلى، فالبوت جاهز. إذا رأيت أخطاء، فالمشكلة في المفاتيح.</p>
        <button onclick="window.location.reload()" style="padding:10px 20px; background:#f0b90b; border:none; border-radius:5px; cursor:pointer;">إعادة الفحص</button>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
