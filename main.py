# main.py - Trading Bot Pro v8.1 FINAL لـ Render.com
import os
import time
import logging
from datetime import datetime
import sys
try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger(__name__)

class TradingBotProV81:
    def __init__(self):
        self.api_key = os.getenv('OiPl7xWT2zOuZMu2for53DDmJvludenpCiIOghBW4KKfQksOwCOHZmVCUsGeQCI3')
        self.api_secret = os.getenv('D83WGpMFTUOl38r6VdeUlEJfVx32YHIVSFFCGp4qXnMOZMuNyV0WScZH2gP09BeI')
        self.symbol = os.getenv('SYMBOL', 'BTCUSDT')
        self.trade_amount = float(os.getenv('TRADE_AMOUNT', '0.001'))
        
        self.client = None
        self.connect()
        
    def connect(self):
        if self.api_key and self.api_secret and BINANCE_AVAILABLE:
            try:
                self.client = Client(self.api_key, self.api_secret, testnet=True)
                self.client.ping()
                logger.info(f"✅ Binance Testnet Connected - {self.symbol}")
                self.live_mode = True
            except Exception as e:
                logger.error(f"❌ Binance Connection Failed: {e}")
                self.live_mode = False
        else:
            logger.info("🧪 Test Mode Active")
            self.live_mode = False
    
    def get_price(self):
        if self.live_mode and self.client:
            try:
                ticker = self.client.get_symbol_ticker(symbol=self.symbol)
                return float(ticker['price'])
            except:
                pass
        # Fallback test price
        import random
        return round(45000 + random.randint(-1000, 1000), 2)
    
    def trading_cycle(self):
        price = self.get_price()
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        status = "🔥 LIVE" if self.live_mode else "🧪 TEST"
        action = "HOLD"
        
        logger.info(f"{status} | {self.symbol} ${price:,.2f} | {action} | {timestamp}")
        return action

def main():
    logger.info("=" * 60)
    logger.info("🚀 TRADING BOT PRO v8.1 - Render.com LIVE")
    logger.info(f"📅 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    bot = TradingBotProV81()
    
    cycle = 0
    while True:
        try:
            bot.trading_cycle()
            cycle += 1
            logger.info(f"✅ Cycle #{cycle} - Bot Running 24/7")
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("🛑 Graceful shutdown")
            break
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    main()
