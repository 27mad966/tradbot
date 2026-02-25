# main.py - Trading Bot Pro v8.1 لـ Render.com (بدون FastAPI)
"""
🚀 Trading Bot Pro v8.1 - نسخة Render.com النهائية
لا حاجة لـ FastAPI - تشغيل مباشر كـ Background Worker
"""

import os
import time
import logging
import sys
from datetime import datetime

# إنشاء الكلاس مباشرة هنا (بدون ملفات منفصلة)
class TradingBotProV81:
    def __init__(self):
        self.api_key = os.getenv('BINANCE_TESTNET_API_KEY')
        self.api_secret = os.getenv('BINANCE_TESTNET_SECRET_KEY')
        self.symbol = os.getenv('SYMBOL', 'BTCUSDT')
        self.trade_amount = float(os.getenv('TRADE_AMOUNT', '0.001'))
        
        print(f"🚀 Bot started: {self.symbol}")
        print("✅ Environment variables loaded successfully")
        
        # محاكاة العمل (للاختبار على Render)
        self.running = True
        
    def trading_cycle(self):
        """دورة تداول واحدة"""
        current_time = datetime.now().strftime("%H:%M:%S")
        print(f"📊 Trading cycle at {current_time} - {self.symbol}")
        print(f"💰 Amount: {self.trade_amount}")
        return "HOLD"
    
    def run_forever(self):
        """حلقة التداول الدائمة"""
        cycle_count = 0
        while True:
            try:
                action = self.trading_cycle()
                cycle_count += 1
                print(f"✅ Cycle #{cycle_count} - Action: {action}")
                time.sleep(60)  # كل دقيقة
            except KeyboardInterrupt:
                print("🛑 Bot stopped")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                time.sleep(30)

def main():
    """الدالة الرئيسية - تعمل على Render.com"""
    print("=" * 60)
    print("🚀 TRADING BOT PRO v8.1 - Render.com Edition")
    print("📅 Started:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("🌍 Binance Testnet Mode")
    print("=" * 60)
    
    # فحص المفاتيح
    if not os.getenv('BINANCE_TESTNET_API_KEY'):
        print("❌ ERROR: BINANCE_TESTNET_API_KEY missing!")
        sys.exit(1)
    
    # بدء البوت
    bot = TradingBotProV81()
    bot.run_forever()

if __name__ == "__main__":
    main()
