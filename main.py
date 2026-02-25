# main.py - النسخة النهائية مع Test Mode
import os
import time
import logging
from datetime import datetime
import sys

# إعداد Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TradingBotProV81:
    def __init__(self):
        self.api_key = os.getenv('BINANCE_TESTNET_API_KEY')
        self.api_secret = os.getenv('BINANCE_TESTNET_SECRET_KEY')
        self.symbol = os.getenv('SYMBOL', 'BTCUSDT')
        self.trade_amount = float(os.getenv('TRADE_AMOUNT', '0.001'))
        
        # فحص المفاتيح مع Test Mode
        if not self.api_key:
            logger.warning("⚠️  TEST MODE - No API Key (محاكاة التداول)")
            self.test_mode = True
        else:
            logger.info("✅ Live Mode - API Keys loaded")
            self.test_mode = False
            
    def get_price(self):
        """محاكاة السعر أو الحصول عليه الحقيقي"""
        if self.test_mode:
            import random
            return round(45000 + random.randint(-500, 500), 2)
        # الكود الحقيقي هنا لاحقاً
        return 45000.0
    
    def trading_cycle(self):
        current_price = self.get_price()
        current_time = datetime.now().strftime("%H:%M:%S")
        
        if self.test_mode:
            action = "HOLD"
            logger.info(f"🧪 TEST | {self.symbol} ${current_price} | {action} | {current_time}")
        else:
            action = "LIVE"
            logger.info(f"🔥 LIVE | {self.symbol} ${current_price} | {action} | {current_time}")
            
        return action

def main():
    print("=" * 60)
    print("🚀 TRADING BOT PRO v8.1 - Render.com LIVE")
    print("📅 Started:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)
    
    bot = TradingBotProV81()
    
    cycle = 0
    while True:
        try:
            action = bot.trading_cycle()
            cycle += 1
            print(f"✅ Cycle #{cycle} - Status: OK")
            time.sleep(60)  # كل دقيقة
        except KeyboardInterrupt:
            print("🛑 Bot stopped gracefully")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
