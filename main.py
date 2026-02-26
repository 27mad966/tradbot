import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import threading
import time
import random
from datetime import datetime
import json

class TradingBot:
    def __init__(self):
        self.balance = 10000.0  # الرصيد الأساسي
        self.initial_balance = self.balance
        self.trades = []
        self.is_trading = False
        self.app = None
        
    def execute_trade(self, pair, direction, amount):
        """تنفيذ صفقة تداول"""
        if amount > self.balance:
            return False, "الرصيد غير كافي"
            
        # محاكاة نتيجة التداول (عشوائية للتوضيح)
        success_rate = 0.65  # نسبة نجاح افتراضية
        win = random.random() < success_rate
        
        if win:
            profit = amount * random.uniform(0.75, 1.5)
            self.balance += profit
            result = f"✅ ربح: ${profit:.2f}"
        else:
            loss = amount * random.uniform(0.5, 0.95)
            self.balance -= loss
            result = f"❌ خسارة: ${loss:.2f}"
        
        trade = {
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'pair': pair,
            'direction': direction,
            'amount': amount,
            'result': result,
            'balance_after': self.balance
        }
        self.trades.append(trade)
        return True, result

class TradingDashboard:
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        self.bot = TradingBot()
        self.setup_ui()
        
    def setup_ui(self):
        self.app = ctk.CTk()
        self.app.title("نظام تداول آلي مع لوحة تحكم - Trading Bot Dashboard")
        self.app.geometry("1200x800")
        self.app.resizable(True, True)
        
        # الشريط العلوي
        self.create_header()
        
        # لوحة المعلومات الرئيسية
        self.create_main_dashboard()
        
        # لوحة التحكم في التداول
        self.create_trading_panel()
        
        # جدول السجل
        self.create_trade_history()
        
        # بدء تحديث البيانات
        self.update_loop()
        
    def create_header(self):
        header_frame = ctk.CTkFrame(self.app)
        header_frame.pack(fill="x", padx=10, pady=5)
        
        title = ctk.CTkLabel(header_frame, text="🤖 نظام التداول الآلي", 
                           font=ctk.CTkFont(size=24, weight="bold"))
        title.pack(pady=10)
        
        status_frame = ctk.CTkFrame(header_frame)
        status_frame.pack(fill="x", padx=20, pady=5)
        
        self.status_label = ctk.CTkLabel(status_frame, text="⏹️ متوقف", 
                                       font=ctk.CTkFont(size=16, weight="bold"))
        self.status_label.pack(side="left", padx=20)
        
        self.balance_label = ctk.CTkLabel(status_frame, text=f"💰 الرصيد: ${self.bot.balance:.2f}",
                                        font=ctk.CTkFont(size=20, weight="bold"))
        self.balance_label.pack(side="right", padx=20)
        
    def create_main_dashboard(self):
        dash_frame = ctk.CTkFrame(self.app)
        dash_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # معلومات الحساب
        account_frame = ctk.CTkFrame(dash_frame)
        account_frame.pack(side="left", fill="both", expand=True, padx=(0,10))
        
        ctk.CTkLabel(account_frame, text="📊 معلومات الحساب", 
                    font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
        
        info_frame = ctk.CTkFrame(account_frame)
        info_frame.pack(fill="x", padx=20, pady=10)
        
        self.initial_balance_label = ctk.CTkLabel(info_frame, text=f"الرصيد الأولي: ${self.bot.initial_balance:.2f}")
        self.initial_balance_label.pack(pady=5)
        
        self.profit_loss_label = ctk.CTkLabel(info_frame, text="الربح/الخسارة: $0.00 (0%)")
        self.profit_loss_label.pack(pady=5)
        
        self.win_rate_label = ctk.CTkLabel(info_frame, text="نسبة الفوز: 0% (0/0)")
        self.win_rate_label.pack(pady=5)
        
        self.total_trades_label = ctk.CTkLabel(info_frame, text="إجمالي الصفقات: 0")
        self.total_trades_label.pack(pady=5)
        
        # أزرار التحكم السريع
        control_frame = ctk.CTkFrame(account_frame)
        control_frame.pack(fill="x", padx=20, pady=20)
        
        self.start_button = ctk.CTkButton(control_frame, text="▶️ بدء التداول", 
                                        command=self.start_trading,
                                        font=ctk.CTkFont(size=16, weight="bold"),
                                        height=40)
        self.start_button.pack(side="left", padx=10, pady=10, fill="x", expand=True)
        
        self.stop_button = ctk.CTkButton(control_frame, text="⏹️ إيقاف التداول", 
                                       command=self.stop_trading,
                                       font=ctk.CTkFont(size=16, weight="bold"),
                                       height=40)
        self.stop_button.pack(side="right", padx=10, pady=10, fill="x", expand=True)
        
    def create_trading_panel(self):
        trading_frame = ctk.CTkFrame(self.app)
        trading_frame.pack(fill="x", padx=10, pady=(0,10))
        
        ctk.CTkLabel(trading_frame, text="⚙️ إعدادات التداول", 
                    font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
        
        settings_frame = ctk.CTkFrame(trading_frame)
        settings_frame.pack(fill="x", padx=20, pady=10)
        
        # خيارات العملات
        pair_frame = ctk.CTkFrame(settings_frame)
        pair_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(pair_frame, text="الزوج:").pack(side="left", padx=10)
        self.pair_var = ctk.StringVar(value="EUR/USD")
        pairs = ["EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "ETH/USD"]
        self.pair_combo = ctk.CTkComboBox(pair_frame, values=pairs, variable=self.pair_var)
        self.pair_combo.pack(side="right", padx=10)
        
        # المبلغ
        amount_frame = ctk.CTkFrame(settings_frame)
        amount_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(amount_frame, text="المبلغ ($):").pack(side="left", padx=10)
        self.amount_var = ctk.StringVar(value="100")
        amount_entry = ctk.CTkEntry(amount_frame, textvariable=self.amount_var, width=100)
        amount_entry.pack(side="right", padx=10)
        
        # اتجاه الصفقة
        direction_frame = ctk.CTkFrame(settings_frame)
        direction_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(direction_frame, text="الاتجاه:").pack(side="left", padx=10)
        self.direction_var = ctk.StringVar(value="CALL")
        direction_combo = ctk.CTkComboBox(direction_frame, values=["CALL", "PUT"], 
                                        variable=self.direction_var, width=100)
        direction_combo.pack(side="right", padx=10)
        
        # زر تنفيذ صفقة يدوية
        manual_trade_btn = ctk.CTkButton(settings_frame, text="🎯 تنفيذ صفقة يدوية", 
                                       command=self.manual_trade,
                                       font=ctk.CTkFont(size=14, weight="bold"),
                                       height=35)
        manual_trade_btn.pack(pady=15)
        
    def create_trade_history(self):
        history_frame = ctk.CTkScrollableFrame(self.app, height=200)
        history_frame.pack(fill="both", expand=True, padx=10, pady=(0,10))
        
        ctk.CTkLabel(history_frame, text="📋 سجل الصفقات", 
                    font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
        
        self.history_listbox = tk.Listbox(history_frame, height=8, font=("Arial", 10))
        self.history_listbox.pack(fill="both", expand=True, padx=20, pady=10)
        
    def start_trading(self):
        if not self.bot.is_trading:
            self.bot.is_trading = True
            self.status_label.configure(text="▶️ يعمل")
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            threading.Thread(target=self.auto_trading_loop, daemon=True).start()
    
    def stop_trading(self):
        self.bot.is_trading = False
        self.status_label.configure(text="⏹️ متوقف")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
    
    def manual_trade(self):
        try:
            amount = float(self.amount_var.get())
            if amount <= 0 or amount > self.bot.balance:
                messagebox.showerror("خطأ", "المبلغ غير صالح أو الرصيد غير كافي")
                return
                
            pair = self.pair_var.get()
            direction = self.direction_var.get()
            
            success, result = self.bot.execute_trade(pair, direction, amount)
            if success:
                self.update_dashboard()
                messagebox.showinfo("نجح", result)
            else:
                messagebox.showerror("خطأ", result)
        except ValueError:
            messagebox.showerror("خطأ", "يرجى إدخال مبلغ صحيح")
    
    def auto_trading_loop(self):
        """حلقة التداول التلقائي"""
        while self.bot.is_trading:
            try:
                amount = 50  # مبلغ ثابت للتداول التلقائي
                pair = random.choice(["EUR/USD", "GBP/USD", "USD/JPY"])
                direction = random.choice(["CALL", "PUT"])
                
                success, result = self.bot.execute_trade(pair, direction, amount)
                self.update_dashboard()
                
                time.sleep(3)  # انتظار 3 ثواني بين الصفقات
            except:
                break
    
    def update_dashboard(self):
        """تحديث لوحة التحكم"""
        # تحديث الرصيد
        self.balance_label.configure(text=f"💰 الرصيد: ${self.bot.balance:.2f}")
        
        # حساب الأرباح/الخسائر
        pnl = self.bot.balance - self.bot.initial_balance
        pnl_percent = (pnl / self.bot.initial_balance) * 100
        pnl_color = "green" if pnl >= 0 else "red"
        self.profit_loss_label.configure(text=f"الربح/الخسارة: ${pnl:.2f} ({pnl_percent:.2f}%)")
        
        # نسبة الفوز
        total_trades = len(self.bot.trades)
        wins = sum(1 for trade in self.bot.trades if "✅" in trade['result'])
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        self.win_rate_label.configure(text=f"نسبة الفوز: {win_rate:.1f}% ({wins}/{total_trades})")
        
        self.total_trades_label.configure(text=f"إجمالي الصفقات: {total_trades}")
        
        # تحديث سجل الصفقات
        self.history_listbox.delete(0, tk.END)
        for trade in self.bot.trades[-10:]:  # آخر 10 صفقات
            self.history_listbox.insert(tk.END, f"{trade['time']} | {trade['pair']} | {trade['direction']} | {trade['amount']}$ | {trade['result']}")
    
    def update_loop(self):
        """حلقة التحديث الدوري"""
        self.update_dashboard()
        self.app.after(1000, self.update_loop)  # تحديث كل ثانية
    
    def run(self):
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.app.mainloop()
    
    def on_closing(self):
        self.bot.is_trading = False
        self.app.quit()

if __name__ == "__main__":
    app = TradingDashboard()
    app.run()
