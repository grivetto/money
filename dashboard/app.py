from flask import Flask, jsonify, render_template_string
import json
import os
import sqlite3
import logging
from datetime import datetime

app = Flask(__name__)
BASE = "/home/sergio/denaro"

logging.basicConfig(level=logging.INFO)

def get_capital():
    try:
        path = os.path.join(BASE, "liquidity_config.json")
        logging.info(f"Attempting to read capital from {path}")
        if not os.path.exists(path):
            logging.error("File not found")
            return 0
        with open(path, 'r') as f:
            data = json.load(f)
            val = data.get("total_capital_eur", 0)
            logging.info(f"Found capital: {val}")
            return round(val, 2)
    except Exception as e:
        logging.error(f"get_capital error: {e}")
        return 0

def get_daily_profit():
    try:
        path = os.path.join(BASE, "trades.db")
        logging.info(f"Attempting to read profit from {path}")
        if not os.path.exists(path):
            logging.error("DB not found")
            return 0
        conn = sqlite3.connect(path)
        c = conn.cursor()
        today = datetime.now().strftime("%Y-%m-%d")
        # Query più robusta per diverse versioni di SQLite
        c.execute("SELECT SUM(profit) FROM trades WHERE timestamp LIKE ?", (f"{today}%",))
        res = c.fetchone()[0]
        conn.close()
        logging.info(f"Found profit: {res}")
        return round(res if res else 0, 2)
    except Exception as e:
        logging.error(f"get_daily_profit error: {e}")
        return 0

def get_active_bots():
    import subprocess
    try:
        r = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        bots = []
        for line in r.stdout.split("\n"):
            if ("realistic_grid_bot" in line or "eur_usdt_scalper" in line or "denaro_ultimate.py" in line):
                if "grep" not in line:
                    symbol = "Unknown"
                    if "SOLEUR" in line or "SOLUSDT" in line: symbol = "SOL/USDT"
                    elif "ETHEUR" in line or "ETHUSDT" in line: symbol = "ETH/USDT"
                    elif "BTCEUR" in line or "BTCUSDT" in line: symbol = "BTC/USDT"
                    bots.append({"name": symbol, "status": "ACTIVE"})
        return bots
    except Exception as e:
        logging.error(f"get_active_bots error: {e}")
        return []

HTML_TEMPLATE = \"\"\"
<!DOCTYPE html>
<html lang='en'>
<head>
    <meta charset='UTF-8'>
    <meta name='viewport' content='width=device-width, initial-scale=1.0'>
    <title>DENARO | Quant Dashboard</title>
    <style>
        :root {
            --bg-color: #0a0a0c;
            --card-bg: #141417;
            --neon-green: #00ff41;
            --neon-blue: #00d4ff;
            --text-main: #e0e0e0;
            --text-dim: #888;
            --danger: #ff3131;
        }
        body {
            background-color: var(--bg-color);
            color: var(--text-main);
            font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            margin: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
        }
        .header {
            width: 100%;
            padding: 20px;
            text-align: center;
            border-bottom: 1px solid #333;
            background: linear-gradient(180deg, #1a1a1f 0%, var(--bg-color) 100%);
        }
        .header h1 {
            margin: 0;
            font-size: 1.8rem;
            letter-spacing: 4px;
            color: var(--neon-blue);
            text-shadow: 0 0 10px var(--neon-blue);
        }
        .grid-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            width: 90%;
            max-width: 1200px;
            margin-top: 30px;
        }
        .card {
            background: var(--card-bg);
            border: 1px solid #333;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.5);
            transition: transform 0.2s;
            position: relative;
            overflow: hidden;
        }
        .card:hover { transform: translateY(-5px); border-color: var(--neon-blue); }
        .card-title {
            color: var(--text-dim);
            font-size: 0.9rem;
            text-transform: uppercase;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .card-value {
            font-size: 2.5rem;
            font-weight: bold;
            font-family: 'Courier New', monospace;
        }
        .value-green { color: var(--neon-green); text-shadow: 0 0 10px var(--neon-green); }
        .value-blue { color: var(--neon-blue); text-shadow: 0 0 10px var(--neon-blue); }
        .value-red { color: var(--danger); text-shadow: 0 0 10px var(--danger); }

        .bot-list {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        .bot-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #222;
        }
        .bot-item:last-child { border-bottom: none; }
        .status-indicator {
            width: 8px;
            height: 8px;
            background: var(--neon-green);
            border-radius: 50%;
            display: inline-block;
            margin-right: 10px;
            box-shadow: 0 0 8px var(--neon-green);
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(1.2); }
            100% { opacity: 1; transform: scale(1); }
        }
        .footer {
            margin-top: auto;
            padding: 20px;
            color: var(--text-dim);
            font-size: 0.8rem;
        }
    </style>
    <script>
        async function updateStats() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();
                
                document.getElementById('capital').innerText = data.capital + '€';
                
                const profitEl = document.getElementById('profit');
                profitEl.innerText = (data.daily_profit >= 0 ? '+' : '') + data.daily_profit + '€';
                profitEl.className = 'card-value ' + (data.daily_profit >= 0 ? 'value-green' : 'value-red');
                
                const botList = document.getElementById('bot-list');
                botList.innerHTML = '';
                if (data.bots.length === 0) {
                    botList.innerHTML = '<li class=\\"bot-item\\">Sincronizzazione flotta...</li>';
                } else {
                    data.bots.forEach(bot => {
                        const li = document.createElement('li');
                        li.className = 'bot-item';
                        li.innerHTML = '<span><span class=\\"status-indicator\\\"></span>' + bot.name + '</span><span style=\\"color: var(--neon-green); font-size: 0.8rem;\\">RUNNING</span>';
                        botList.appendChild(li);
                    });
                }
            } catch (e) {
                console.error('Error fetching stats:', e);
            }
        }
        setInterval(updateStats, 5000);
        window.onload = updateStats;
    </script>
</head>
<body>
    <div class='header'>
        <h1>DENARO <span style='font-weight: 100; font-size: 1rem; color: #666;'>| QUANT INFRASTRUCTURE</span></h1>
    </div>
    <div class='grid-container'>
        <div class='card'>
            <div class='card-title'>💰 TOTAL CAPITAL</div>
            <div id='capital' class='card-value value-blue'>0.00€</div>
        </div>
        <div class='card'>
            <div class='card-title'>📈 DAILY REAL PROFIT</div>
            <div id='profit' class='card-value'>0.00€</div>
        </div>
        <div class='card'>
            <div class='card-title'>🤖 ACTIVE FLEET</div>
            <ul id='bot-list' class='bot-list'>
                <li class='bot-item'>Loading bots...</li>
            </ul>
        </div>
    </div>
    <div class='footer'>
        SISTEMA OPERATIVO | REAL-TIME ACCOUNTING ENABLED | HEARTBEAT ACTIVE
    </div>
</body>
</html>
\"\"\"

@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route("/api/status")
def status():
    return jsonify({
        "status": "online",
        "capital": get_capital(),
        "daily_profit": get_daily_profit(),
        "bots": get_active_bots(),
        "timestamp": datetime.now().isoformat()
    })

@app.route("/api/capital")
def capital():
    return jsonify({"eur_equivalent": get_capital()})

@app.route("/api/profit")
def profit():
    return jsonify({"daily": get_daily_profit()})

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=8443)
