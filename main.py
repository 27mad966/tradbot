<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Bot Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 100%); color: white; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { text-align: center; margin-bottom: 30px; color: #00ff88; }
        .status { display: flex; gap: 20px; margin-bottom: 30px; }
        .status-card { flex: 1; background: rgba(255,255,255,0.1); padding: 20px; border-radius: 15px; text-align: center; }
        .status-card.green { border: 2px solid #00ff88; }
        .profit { color: #00ff88; font-size: 2em; font-weight: bold; }
        .loss { color: #ff4444; font-size: 2em; font-weight: bold; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat { background: rgba(255,255,255,0.1); padding: 20px; border-radius: 15px; text-align: center; }
        table { width: 100%; border-collapse: collapse; background: rgba(255,255,255,0.1); border-radius: 15px; overflow: hidden; }
        th, td { padding: 15px; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.2); }
        th { background: rgba(0,255,136,0.2); }
        tr.open { background: rgba(0,255,0,0.1); }
        tr.closed { background: rgba(255,255,255,0.05); }
        tr:hover { background: rgba(255,255,255,0.1); }
        .live { color: #00ff88; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🟢 Live Trading Dashboard</h1>
        
        <div class="status">
            <div class="status-card {{ 'green' if balance.testnet else '' }}">
                <h3>{{ 'Binance Testnet' if balance.testnet else 'Binance Live' }}</h3>
                <div class="live">{{ '🟢 متصل' if balance.usdt else '🔴 خطأ' }}</div>
            </div>
            <div class="status-card">
                <h3>رصيد USDT</h3>
                <div>{{ "%.2f"|format(balance.usdt|default(0)) }}</div>
            </div>
        </div>

        <div class="stats">
            <div class="stat">
                <h3>الربح الإجمالي</h3>
                <span class="{{ 'profit' if total_profit >= 0 else 'loss' }}">{{ "%.2f"|format(total_profit) }} USDT</span>
            </div>
            <div class="stat">
                <h3>صفقات مفتوحة</h3>
                <span>{{ open_trades }}</span>
            </div>
            <div class="stat">
                <h3>صفقات مغلقة</h3>
                <span>{{ closed_trades }}</span>
            </div>
        </div>

        <h2>📊 آخر 10 صفقات:</h2>
        <table>
            <tr>
                <th>النوع</th>
                <th>الزوج</th>
                <th>السعر</th>
                <th>الكمية</th>
                <th>سعر البيع</th>
                <th>الربح</th>
                <th>التاريخ</th>
            </tr>
            {% for trade in recent_trades %}
            <tr class="{{ 'open' if trade.status == 'OPEN' else 'closed' }}">
                <td>{{ trade.type }}</td>
                <td>{{ trade.symbol }}</td>
                <td>${{ "%.4f"|format(trade.price) }}</td>
                <td>{{ "%.4f"|format(trade.amount) }}</td>
                <td>{{ "%.4f"|format(trade.sell_price|default(0)) }}</td>
                <td class="{{ 'profit' if trade.profit > 0 else 'loss' }}">
                    {% if trade.profit is defined %}{{ "%.2f"|format(trade.profit) }} USDT{% endif %}
                </td>
                <td>{{ trade.timestamp[:16] }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>

    <script>
        setInterval(async () => {
            location.reload();
        }, 5000); // تحديث كل 5 ثواني
    </script>
</body>
</html>
