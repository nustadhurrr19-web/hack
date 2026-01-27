from flask import Flask, render_template_string, jsonify
import json
import os
import time

app = Flask(__name__)
DASHBOARD_FILE = 'dashboard_data.json'

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TITAN GHOST UI</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&display=swap');
        
        body { 
            background-color: #050505; 
            color: #e0e0e0; 
            font-family: 'JetBrains Mono', monospace; 
            margin: 0; 
            padding: 20px 0 50px 0; 
            display: flex;
            justify-content: center;
        }

        .container { 
            width: 90%; 
            max-width: 500px; 
            text-align: center; 
            border: 1px solid #222; 
            padding: 25px; 
            border-radius: 12px; 
            background: #0a0a0a;
            box-shadow: 0 0 20px rgba(0,0,0,0.8);
        }

        /* --- HEADER --- */
        .header { 
            font-size: 12px; 
            color: #555; 
            letter-spacing: 3px; 
            margin-bottom: 25px; 
            text-transform: uppercase; 
            border-bottom: 1px solid #222;
            padding-bottom: 15px;
        }

        /* --- STATS GRID --- */
        .stats-grid { 
            display: grid; 
            grid-template-columns: repeat(3, 1fr); 
            gap: 10px; 
            margin-bottom: 25px; 
        }
        .stat-box { 
            background: #111; 
            padding: 10px; 
            border-radius: 6px; 
            border: 1px solid #1a1a1a;
        }
        .stat-label { font-size: 9px; color: #666; display: block; margin-bottom: 4px; }
        .stat-val { font-size: 16px; font-weight: bold; color: #fff; }
        .acc-green { color: #00ff41; text-shadow: 0 0 10px rgba(0,255,65,0.2); }

        /* --- MAIN PREDICTION --- */
        .period-display { font-size: 12px; color: #444; margin-bottom: 5px; }
        
        .prediction-box { 
            font-size: 65px; 
            font-weight: 800; 
            margin: 10px 0 20px 0; 
            text-transform: uppercase; 
            line-height: 1;
        }
        .pred-big { color: #00ff41; text-shadow: 0 0 30px rgba(0, 255, 65, 0.15); }
        .pred-small { color: #ff0055; text-shadow: 0 0 30px rgba(255, 0, 85, 0.15); }
        .pred-skip { color: #333; }

        /* --- INFO ROW --- */
        .info-grid { 
            display: grid; 
            grid-template-columns: 1fr 1fr 1fr; 
            gap: 8px; 
            margin-bottom: 30px; 
        }
        .info-item { background: #111; padding: 8px; border-radius: 4px; border: 1px solid #1a1a1a; }
        .info-label { font-size: 8px; color: #555; display: block; }
        .info-val { font-size: 12px; font-weight: 700; color: #ccc; }

        /* --- HISTORY LIST --- */
        .history-container {
            text-align: left;
            border-top: 1px solid #222;
            padding-top: 20px;
        }
        .history-title { font-size: 10px; color: #555; margin-bottom: 10px; letter-spacing: 1px; }
        
        .history-header {
            display: grid;
            grid-template-columns: 1.5fr 1fr 1.5fr 1fr;
            padding: 5px 10px;
            font-size: 9px;
            color: #444;
            font-weight: bold;
        }

        .history-item { 
            display: grid; 
            grid-template-columns: 1.5fr 1fr 1.5fr 1fr;
            padding: 8px 10px; 
            border-bottom: 1px solid #141414; 
            font-size: 12px;
            align-items: center;
        }
        .history-item:nth-child(odd) { background-color: #0d0d0d; }

        .h-period { color: #666; font-size: 11px; }
        .h-pred { font-weight: bold; }
        .h-level { font-size: 10px; color: #888; }
        
        /* RESULT COLORS */
        .res-win { color: #00ff41; font-weight: bold; }
        .res-loss { color: #ff0055; font-weight: bold; }
        .res-none { color: #333; }

        /* LEVEL COLORS */
        .lvl-ghost { color: #a200ff; }
        .lvl-safe { color: #00d9ff; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">TITAN V2026 // GHOST CONTROLLER</div>
        
        <div class="stats-grid">
            <div class="stat-box">
                <span class="stat-label">SESSION WINS</span>
                <span class="stat-val" id="wins">0</span>
            </div>
            <div class="stat-box">
                <span class="stat-label">SESSION LOSS</span>
                <span class="stat-val" id="losses">0</span>
            </div>
            <div class="stat-box">
                <span class="stat-label">ACCURACY</span>
                <span class="stat-val acc-green" id="accuracy">0.0%</span>
            </div>
        </div>

        <div class="period-display" id="period">PERIOD: ---</div>
        <div id="prediction" class="prediction-box pred-skip">---</div>
        
        <div class="info-grid">
            <div class="info-item">
                <span class="info-label">STATUS</span>
                <span class="info-val" id="status-text">INIT</span>
            </div>
            <div class="info-item">
                <span class="info-label">TIMER</span>
                <span class="info-val" id="timer">--</span>
            </div>
            <div class="info-item">
                <span class="info-label">LEVEL</span>
                <span class="info-val" id="level-display">---</span>
            </div>
        </div>

        <div class="history-container">
            <div class="history-title">RECENT TRAJECTORY</div>
            <div class="history-header">
                <span>ISSUE</span>
                <span>PRED</span>
                <span>LEVEL</span>
                <span style="text-align:right;">RES</span>
            </div>
            <div id="history-list">
                </div>
        </div>
    </div>

    <script>
        function updateData() {
            fetch('/data')
                .then(response => response.json())
                .then(data => {
                    // 1. Update Header Info
                    document.getElementById('period').innerText = "PERIOD: " + data.period;
                    document.getElementById('status-text').innerText = data.status_text;
                    document.getElementById('timer').innerText = data.timer + "s";
                    document.getElementById('level-display').innerText = data.level;

                    // 2. Update Prediction Big Display
                    const predEl = document.getElementById('prediction');
                    predEl.innerText = data.prediction;
                    
                    let predClass = 'pred-skip';
                    if (data.prediction === 'BIG') predClass = 'pred-big';
                    if (data.prediction === 'SMALL') predClass = 'pred-small';
                    predEl.className = 'prediction-box ' + predClass;
                    
                    // 3. Update Stats
                    if (data.stats) {
                        document.getElementById('wins').innerText = data.stats.wins;
                        document.getElementById('losses').innerText = data.stats.losses;
                        document.getElementById('accuracy').innerText = data.stats.accuracy;
                    }

                    // 4. Update History List
                    const hList = document.getElementById('history-list');
                    hList.innerHTML = ""; // Clear current list
                    
                    if (data.history && data.history.length > 0) {
                        data.history.forEach(item => {
                            const row = document.createElement('div');
                            row.className = 'history-item';
                            
                            // Formatting
                            const issueShort = item.period.slice(-4);
                            const resultClass = item.result === "WIN" ? "res-win" : (item.result === "LOSS" ? "res-loss" : "res-none");
                            
                            // Color code the levels slightly
                            let levelClass = "";
                            if(item.level === "GHOST_SIM") levelClass = "lvl-ghost";
                            
                            row.innerHTML = `
                                <span class="h-period">${issueShort}</span>
                                <span class="h-pred">${item.pred}</span>
                                <span class="h-level ${levelClass}">${item.level || '---'}</span>
                                <span class="${resultClass}" style="text-align:right;">${item.result}</span>
                            `;
                            hList.appendChild(row);
                        });
                    } else {
                        hList.innerHTML = "<div style='padding:10px; font-size:10px; color:#444; text-align:center;'>NO HISTORY YET</div>";
                    }
                })
                .catch(err => console.log("Waiting for backend..."));
        }
        setInterval(updateData, 1000); 
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/data')
def get_data():
    try:
        if os.path.exists(DASHBOARD_FILE):
            with open(DASHBOARD_FILE, 'r') as f:
                return jsonify(json.load(f))
    except: pass
    # Default fallback structure
    return jsonify({
        "period": "---", 
        "prediction": "WAITING", 
        "level": "---",
        "timer": 0,
        "status_text": "OFFLINE",
        "history": [], 
        "stats": {"wins":0, "losses":0, "accuracy":"0%"}
    })

if __name__ == '__main__':
    app.run(debug=True, port=5012)
