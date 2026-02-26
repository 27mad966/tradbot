import os
import ccxt
import time
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

class OfficialBinanceBot:
    def __init__(self):
        # وضع المفاتيح يدوياً هنا هو "أقصر طريق" للتأكد من صحتها بعيداً عن تعقيدات ريندر
        self.api_key = "XnEm0wn9uAFLpwFAXZZ3UhkFAWiYgWU5h5fIRnucvVoylC6BfPEabdKDJ9u8NX5Q"
        self.secret_key = "YFOf0OwhIpHIlDiaPDGfkLCHypLYEk9uHAt0AMcE7VQ4Kcy065oKQj8eSMjc4CIH"

        # إعداد المكتبة حسب المعايير الرسمية لبايننس
        self.exchange = ccxt.binance({
            'apiKey': self.api_key.strip(),
            'secret': self.secret_key.strip(),
            'enableRateLimit': True,
            'options': {
                'adjustForTimeDifference': True, # مزامنة الوقت إجبارياً
                'recvWindow': 10000, # القيمة القياسية لمنع أخطاء التوقيت
                'defaultType': 'spot'
            }
        })
        # استخدام روابط الـ Vision الرسمية التي ظهرت في صورتك
        self.exchange.urls['api']['public'] = 'https://testnet.binance.vision/api'
        self.exchange.urls['api']['private'] = 'https://testnet.binance.vision/api'

    def get_account_data(self):
        try:
            # طلب معلومات الحساب الأساسية
            balance = self.exchange.fetch_balance()
            # استخراج العملات التي تملك فيها رصيداً فقط
            owned_assets = {coin: data['total'] for coin, data in balance['total'].items() if data > 0}
            
            if owned_assets:
                return f"💰 نجاح! تم العثور على الأرصدة التالية: {owned_assets}"
            else:
                return "✅ المفاتيح صحيحة والمتصل ناجح، ولكن حسابك 'صفر' لا يوجد به أي عملات حالياً."
        except Exception as e:
            # تحليل الخطأ بناءً على رد بايننس الرسمي
            error_msg = str(e)
            if "Invalid Api-Key ID" in error_msg:
                return "❌ بايننس لا تزال ترفض المعرّف. تأكد أنك في Spot Testnet وليس Futures."
            elif "Signature for this request is not valid" in error_msg:
                return "❌ السر (Secret Key) خطأ أو لم يتم نسخه كاملاً."
            return f"❌ خطأ غير متوقع: {error_msg}"

bot = OfficialBinanceBot()

@app.get("/", response_class=HTMLResponse)
async def root():
    status = bot.get_account_data()
    return f"""
    <body style="background:#0b0e11; color:white; font-family:sans-serif; text-align:center; padding-top:100px;">
        <h1 style="color:#f0b90b;">🔍 فحص الاتصال الرسمي</h1>
        <div style="display:inline-block; border:2px solid #333; padding:40px; border-radius:20px; background:#161a1e;">
            <p style="font-size:1.5em;">{status}</p>
        </div>
        <br><br>
        <button onclick="window.location.reload()" style="background:#f0b90b; border:none; padding:10px 30px; border-radius:5px; font-weight:bold; cursor:pointer;">إعادة المحاولة</button>
    </body>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
