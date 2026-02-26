import os
import ccxt
import asyncio
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

class SmartBot:
    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY", "").strip()
        self.secret_key = os.getenv("BINANCE_SECRET_KEY", "").strip()

    async def probe_servers(self):
        reports = []
        # القائمة المستهدفة للفحص: النظام القديم والنظام الجديد
        endpoints = [
            {"name": "Spot Testnet (Vision)", "url": "https://testnet.binance.vision/api"},
            {"name": "Binance Demo (Global)", "url": "https://api.binance.com"} # الديمو الجديد غالباً يستخدم الرابط الرئيسي مع وضع الساندبوكس
        ]

        for server in endpoints:
            try:
                exchange = ccxt.binance({
                    'apiKey': self.api_key,
                    'secret': self.secret_key,
                    'enableRateLimit': True,
                    'options': {'adjustForTimeDifference': True}
                })
                exchange.set_sandbox_mode(True) # تفعيل وضع التجربة
                
                # تغيير الرابط يدوياً للفحص
                exchange.urls['api']['public'] = server['url']
                exchange.urls['api']['private'] = server['url']
                
                bal = exchange.fetch_balance()
                assets = {k: v for k, v in bal['total'].items() if v > 0}
                reports.append(f"✅ {server['name']}: متصل بنجاح! الرصيد المكتشف: {assets}")
                break # إذا نجح الاتصال بواحد، نتوقف
            except Exception as e:
                reports.append(f"❌ {server['name']}: رفض المفاتيح. السبب: {str(e)[:50]}")
        
        return reports

bot_check = SmartBot()

@app.get("/", response_class=HTMLResponse)
async def home():
    results = await bot_check.probe_servers()
    content = "".join([f"<p>{r}</p>" for r in results])
    return f"""
    <body style="background:#0b0e11; color:white; font-family:sans-serif; padding:50px;">
        <h2 style="color:#f0b90b;">نتائج فحص الخوادم الذكي</h2>
        <div style="border:1px solid #444; padding:20px; border-radius:15px; background:#161a1e;">
            {content}
        </div>
        <p style="color:#888; margin-top:20px;">إذا استمر الرفض في الاثنين، فهناك "مسافة مخفية" أو "حرف ناقص" في إعدادات Render لا تراه العين المجردة.</p>
    </body>
    """

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
