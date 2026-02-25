# main.py - Trading Bot Pro v8.1 - النسخة النهائية الجاهزة للتشغيل
"""
🚀 Trading Bot Pro v8.1 - Binance Testnet 
الكود الرئيسي main.py مع دعم Environment Variables كامل
المفاتيح موجودة مسبقاً في البيئة - جاهز للتشغيل مباشرة!
"""

import os
import time
import logging
from datetime import datetime
import signal
import sys
from trading_bot_pro_v8_1 import TradingBotProV81  # استيراد الكلاس الرئيسي

# إعداد الـ Logging الاحترافي
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('trading_bot_pro_main.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MainBotController:
    def __init__(self):
        """الكونترولر الرئيسي للبوت"""
        self.bot = None
        self.running = False
        
    def signal_handler(self, sig, frame):
        """التعامل مع إيقاف البوت بـ Ctrl+C"""
        logger.info("🛑 إشارة إيقاف تم استقبالها...")
        if self.bot:
            logger.info("💾 حفظ الحالة النهائية...")
        self.stop()
        sys.exit(0)

    def start(self):
        """بدء تشغيل البوت"""
        try:
            logger.info("🚀🚀🚀 بدء تشغيل Trading Bot Pro v8.1 🚀🚀🚀")
            
            # إنشاء البوت
            self.bot = TradingBotProV81()
            self.running = True
            
            # إعداد معالج الإشارات للإيقاف الآمن
            signal.signal(signal.SIGINT, self.signal_handler)
            
            logger.info("✅ البوت جاهز ويعمل 24/7...")
            logger.info("⏰ كل دورة تستغرق: {} ثانية".format(
                os.getenv('SLEEP_INTERVAL', '60')
            ))
            logger.info("📈 العملة: {} | المبلغ: {}".format(
                os.getenv('SYMBOL', 'BTCUSDT'),
                os.getenv('TRADE_AMOUNT', '0.001')
            ))
            
            # حلقة التداول الرئيسية
            while self.running:
                try:
                    action = self.bot.trading_strategy()
                    logger.info(f"📊 الإجراء: {action}")
                    time.sleep(int(os.getenv('SLEEP_INTERVAL', '60')))
                    
                except KeyboardInterrupt:
                    logger.info("🛑 تم إيقاف البوت بواسطة المستخدم")
                    break
                except Exception as e:
                    logger.error(f"❌ خطأ في حلقة التداول: {e}")
                    time.sleep(30)
            
        except Exception as e:
            logger.error(f"❌ فشل في بدء البوت: {e}")
            self.show_quick_start()
    
    def stop(self):
        """إيقاف البوت بشكل آمن"""
        self.running = False
        if self.bot and self.bot.client:
            try:
                logger.info("💾 حفظ السجلات النهائية...")
                logger.info("✅ البوت توقف بنجاح")
            except:
                pass

    def show_quick_start(self):
        """عرض تعليمات التشغيل السريع"""
        print("\n" + "="*60)
        print("🚀 تثبيت سريع للمفاتيح (إذا لم تكن موجودة):")
        print("="*60)
        print("1️⃣ تأكد من المكتبات:")
        print("   pip install python-binance pandas numpy python-dotenv")
        print("\n2️⃣ تحقق من Environment Variables:")
        print("   echo $BINANCE_TESTNET_API_KEY")
        print("   echo $BINANCE_TESTNET_SECRET_KEY")
        print("\n3️⃣ إذا لم توجد، أضفها:")
        print("   export BINANCE_TESTNET_API_KEY='your_key'")
        print("   export BINANCE_TESTNET_SECRET_KEY='your_secret'")
        print("\n4️⃣ جرب البوت:")
        print("   python main.py")
        print("="*60)

def main():
    """الدالة الرئيسية"""
    print("🚀 Trading Bot Pro v8.1 - الإصدار النهائي")
    print("📅 التاريخ:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("🌍 Binance Testnet Mode")
    print("-" * 50)
    
    controller = MainBotController()
    controller.start()

if __name__ == "__main__":
    main()
