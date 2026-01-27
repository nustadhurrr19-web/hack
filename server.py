from flask import Flask, render_template_string, jsonify
import json
import os

app = Flask(__name__)
DASHBOARD_FILE = 'dashboard_data.json'

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TITAN ARCHITECT V99</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&display=swap');
        body { background-color: #050505; color: #e0e0e0; font-family: 'JetBrains Mono', monospace; margin: 0; padding: 20px; display: flex; justify-content: center; }
        .container { width: 100%; max-width: 480px; text-align: center; border: 1px solid #222; padding: 20px; border-radius: 12px; background: #0a0a0a; box-shadow: 0 0 30px rgba(0,0,0,0.5); }
        
        /* HEADER */
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid #222; padding-bottom: 10px; }
        .title { font-size: 14px; font-weight: 800; letter-spacing: 1px; color: #fff; }
        .mode-badge { padding: 4px 8px; border-radius: 4px; font-size: 10px; font-weight: bold; }
        .mode-real { background: rgba(0, 255, 65, 0.2); color: #00ff41; border: 1px solid #00ff41; box-shadow: 0 0 10px rgba(0,255,65,0.2); }
        .mode-ghost { background: rgba(162, 0, 255, 0.2); color: #a200ff; border: 1px solid #a200ff; }

        /* STATS */
        .stats-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 20px; }
        .stat-box { background: #111; padding: 10px; border-radius: 6px; border: 1px solid #1a1a1a; }
        .stat-label { font-size: 9px; color: #666; display: block; margin-bottom: 4px; }
        .stat-val { font-size: 14px; font-weight: bold; color: #fff; }

        /* PREDICTION */
        .pred-box { margin: 20px 0; padding: 20px; background: #0e0e0e; border-radius: 8px; border: 1px solid #222; position: relative; }
        .period { font-size: 12px; color: #555; letter-spacing: 2px; }
        .prediction { font-size: 60px; font-weight: 800; margin: 10px 0; line-height: 1; }
        .pred-big { color: #00ff41; text-shadow: 0 0 20px rgba(0,255,65,0.2); }
        .pred-small { color: #ff0055; text-shadow: 0 0 20px rgba(255,0,85,0.2); }
        .pred-skip { color: #333; }
        .timer { font-size: 12px; color: #888; margin-top: 5px; }
        .status-text { font-size: 10px; color: #444; margin-top:10px; text-transform: uppercase; }

        /* ENGINES */
        .engine-label { text-align:left; font-size:10px; color:#555; margin-bottom:5px; border-top: 1px solid #222; padding-top: 15px; }
        .engine-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5px; margin-bottom: 20px; }
        .eng-box { background: #0d0d0d; padding: 8px; border-radius: 4px; border: 1px solid #1f1f1f; font-size: 10px; display: flex; flex-direction: column; justify-content: center; min-height: 40px; }
        .eng-name { color: #555; margin-bottom: 2px; font-size: 8px; letter-spacing: 1px; }
        .eng-val { color: #ccc; font-weight: bold; }

        /* HISTORY */
        .history-list { text-align: left; font-size: 11px; margin-top: 10px; }
        .h-item { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; padding: 8px; border-bottom: 1px solid #141414; align-items: center; }
        .h-item:last-child { border-bottom: none; }
        .res-win { color: #00ff41; } 
        .res-loss { color: #ff0055; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <span class="title">TITAN ARCHITECT</span>
            <span id="mode-badge" class="mode-badge mode-ghost">GHOST MODE</span>
        </div>

        <div class="stats-row">
            <div class="stat-box">
                <span class="stat-label">SESSION WINS</span>
                <span class="stat-val" id="wins">0</span>
            </div>
            <div class="stat-box">
                <span class="stat-label">SESSION LOSS</span>
                <span class="stat-val" id="losses">0</span>
            </div>
            <div class="stat-box">
                <span class="stat-label">LOGIC HEALTH</span>
                <span class="stat-val" id="health">--%</span>
            </div>
        </div>

        <div class="pred-box">
            <div class="period" id="period">PERIOD: ---</div>
            <div id="prediction" class="prediction pred-skip">---</div>
            <div class="timer" id="timer">--</div>
            <div class="status-text" id="status">INIT</div>
        </div>

        <div class="engine-label">TRI-CORE VOTING SYSTEM</div>
        <div class="engine-grid">
            <div class="eng-box"><span class="eng-name">FRACTAL</span><span class="eng-val" id="eng-frac">-</span></div>
            <div class="eng-box"><span class="eng-name">MOMENTUM</span><span class="eng-val" id="eng-mom">-</span></div>
            <div class="eng-box"><span class="eng-name">AI BRAIN</span><span class="eng-val" id="eng-ml">-</span></div>
        </div>

        <div class="engine-label">RECENT TRAJECTORY</div>
        <div class="history-list" id="history-list"></div>
    </div>

    <script>
        function update() {
            fetch('/data').then(r => r.json()).then(data => {
                // Mode Badge
                const badge = document.getElementById('mode-badge');
                badge.innerText = data.mode + " MODE";
                badge.className = "mode-badge " + (data.mode === 'REAL' ? 'mode-real' : 'mode-ghost');

                // Stats
                document.getElementById('wins').innerText = data.stats.wins;
                document.getElementById('losses').innerText = data.stats.losses;
                document.getElementById('health').innerText = data.logic_health;

                // Prediction Display
                document.getElementById('period').innerText = "PERIOD: " + data.period;
                const predEl = document.getElementById('prediction');
                predEl.innerText = data.prediction;
                predEl.className = "prediction " + (data.prediction === 'BIG' ? 'pred-big' : (data.prediction === 'SMALL' ? 'pred-small' : 'pred-skip'));
                
                document.getElementById('timer').innerText = data.timer + "s";
                document.getElementById('status').innerText = data.status_text;

                // Engines
                if(data.engines) {
                    document.getElementById('eng-frac').innerText = data.engines.fractal;
                    document.getElementById('eng-mom').innerText = data.engines.momentum;
                    document.getElementById('eng-ml').innerText = data.engines.ml;
                }

                // History
                const hList = document.getElementById('history-list');
                hList.innerHTML = "";
                data.history.forEach(item => {
                    const row = document.createElement('div');
                    row.className = 'h-item';
                    const resClass = item.result === 'WIN' ? 'res-win' : 'res-loss';
                    const modeColor = item.mode === 'REAL' ? '#00ff41' : '#a200ff';
                    
                    row.innerHTML = `
                        <span>${item.period.slice(-4)}</span>
                        <span>${item.pred}</span>
                        <span style="font-size:9px; text-align:center; color:${modeColor};">${item.mode}</span>
                        <span class="${resClass}" style="text-align:right;">${item.result}</span>
                    `;
                    hList.appendChild(row);
                });
            }).catch(e => {});
        }
        setInterval(update, 1000);
    </script>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

@app.route('/data')
def get_data():
    try:
        if os.path.exists(DASHBOARD_FILE):
            with open(DASHBOARD_FILE, 'r') as f: return jsonify(json.load(f))
    except: pass
    return jsonify({"period":"---", "prediction":"WAITING"})

if __name__ == '__main__':
    # UPDATED: host='0.0.0.0' allows access from localhost and network
    app.run(host='0.0.0.0', port=5000, debug=True)
