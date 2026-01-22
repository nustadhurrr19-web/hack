from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for
import sqlite3, os, json, functools, uuid, hmac, hashlib, base64
import threading, asyncio
from datetime import datetime, timedelta
import encodings.idna  # Render fix

import fetcher  # DO NOT TOUCH

app = Flask(__name__)

# ===================== SECURITY CONFIG =====================
app.secret_key = "TITAN_SECURE_KEY_CHANGE_THIS"
OFFLINE_SECRET = "TITAN_OFFLINE_SECRET_CODE_123"

# --- MASTER KEY CONFIGURATION ---
GLOBAL_MASTER_KEY = "TITAN-GLOBAL-ADMIN-777" 

# ===================== STORAGE PATH =====================
if os.path.exists('/var/lib/data'):
    BASE_DIR = '/var/lib/data'
elif os.path.exists('/data'):
    BASE_DIR = '/data'
else:
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

DB_PATH = os.path.join(BASE_DIR, 'titan_db.sqlite')
DASHBOARD_FILE = os.path.join(BASE_DIR, 'dashboard_data.json')

# ===================== DATABASE =====================
def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def ensure_tables():
    c = db()
    c.execute("""CREATE TABLE IF NOT EXISTS access_keys (
        key_code TEXT PRIMARY KEY,
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT,
        max_devices INTEGER DEFAULT 1,
        bound_device_id TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS blacklisted_keys (
        key_code TEXT PRIMARY KEY,
        reason TEXT,
        banned_at TEXT
    )""")
    c.commit()
    c.close()

ensure_tables()

# ===================== FETCHER THREAD =====================
def run_fetcher():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(fetcher.main_loop())

if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    threading.Thread(target=run_fetcher, daemon=True).start()

# ===================== KEY VALIDATION =====================
def validate_offline_key(key):
    if not key.startswith("TITAN-"):
        return False, "Invalid Key Format"
    try:
        _, payload, sig = key.split('-')
        payload += '=' * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(payload).decode()
        ts, _, name = raw.split('|')
        calc = hmac.new(OFFLINE_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:8].upper()
        if calc != sig: return False, "Invalid Signature"
        if datetime.now() > datetime.fromtimestamp(int(ts)): return False, "Key Expired"
        return True, {"name": name, "expires": datetime.fromtimestamp(int(ts))}
    except: return False, "Corrupt Key"

def login_required(f):
    @functools.wraps(f)
    def wrap(*a, **k):
        if not session.get("auth"): return redirect(url_for("login"))
        return f(*a, **k)
    return wrap

# ===================== ROUTES =====================
@app.route("/login", methods=["GET", "POST"])
def login():
    err = None
    if request.method == "POST":
        key = request.form.get("key", "").strip()
        dev = request.form.get("device")
        
        if key == GLOBAL_MASTER_KEY:
            session["auth"] = True
            session["key"] = "MASTER_ADMIN"
            return redirect("/")

        c = db()
        if c.execute("SELECT 1 FROM blacklisted_keys WHERE key_code=?", (key,)).fetchone():
            err = "KEY BANNED"
        else:
            row = c.execute("SELECT * FROM access_keys WHERE key_code=?", (key,)).fetchone()
            if not row:
                ok, res = validate_offline_key(key)
                if not ok: err = res
                else:
                    c.execute("INSERT INTO access_keys VALUES (?,?,?,?,?,?)",
                              (key, res["name"], datetime.now(), res["expires"], 1, dev))
                    c.commit()
                    row = c.execute("SELECT * FROM access_keys WHERE key_code=?", (key,)).fetchone()

            if row and not err:
                session["auth"] = True
                session["key"] = key
                return redirect("/")
        c.close()

    return f"""
    <body style="background:#050505;color:#00ff41;display:flex;justify-content:center;align-items:center;height:100vh;font-family:'Courier New', monospace;margin:0">
    <form method="post" style="background:#111;padding:40px;border:1px solid #333;text-align:center;width:300px;border-radius:10px;">
    <h2 style="margin-top:0;text-transform:uppercase;color:#fff;letter-spacing:2px;font-size:20px;">TITAN LOGIN</h2>
    <p style="color:#ff0055;font-weight:bold;font-size:12px">{err or ''}</p>
    <input type="hidden" name="device" id="d">
    <input name="key" placeholder="ACCESS KEY" style="padding:15px;width:100%;box-sizing:border-box;background:#000;border:1px solid #333;color:#fff;text-align:center;font-family:monospace;outline:none;font-size:16px;border-radius:5px;"><br><br>
    <button style="padding:15px 30px;width:100%;background:#00ff41;color:#000;border:none;font-weight:bold;cursor:pointer;font-size:16px;border-radius:5px;">AUTHENTICATE</button>
    </form>
    <script>
    let d=localStorage.getItem("dev");if(!d){{d="DEV-"+Date.now();localStorage.setItem("dev",d)}}
    document.getElementById("d").value=d
    </script>
    </body>
    """

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/data")
@login_required
def data():
    try: return jsonify(json.load(open(DASHBOARD_FILE)))
    except: return jsonify({})

@app.route("/")
@login_required
def index():
    return render_template_string(HTML)

# ===================== UI DESIGN =====================
HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TITAN DASHBOARD</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&display=swap" rel="stylesheet">
<style>
    :root {
        --bg: #0a0a0a;
        --card-bg: #111111;
        --text: #ffffff;
        --dim: #555555;
        --green: #00ff41;
        --red: #ff0055;
        --purple: #a855f7;
    }
    body { background: var(--bg); color: var(--text); font-family: 'JetBrains Mono', monospace; margin: 0; padding: 20px; display: flex; justify-content: center; }
    
    .container { width: 100%; max-width: 500px; }

    /* --- TOP STATS GRID (2x2) --- */
    .stats-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 30px; }
    .stat-box { background: var(--card-bg); border-radius: 6px; padding: 15px 10px; text-align: center; border: 1px solid #1a1a1a; }
    .stat-label { font-size: 0.65rem; color: var(--dim); letter-spacing: 1px; margin-bottom: 8px; text-transform: uppercase; font-weight: 700; }
    .stat-val { font-size: 1.4rem; font-weight: 800; color: #fff; }
    
    .text-green { color: var(--green); }
    .text-red { color: var(--red); }
    .text-white { color: #fff; }

    /* --- MAIN PREDICTION --- */
    .pred-section { text-align: center; margin-bottom: 30px; }
    .period-label { color: var(--dim); font-size: 0.9rem; letter-spacing: 1px; margin-bottom: 5px; }
    .main-pred { font-size: 5rem; font-weight: 800; text-transform: uppercase; line-height: 1; margin: 15px 0; letter-spacing: -2px; }
    .glow-green { color: var(--green); text-shadow: 0 0 20px rgba(0,255,65,0.2); }
    .glow-red { color: var(--red); text-shadow: 0 0 20px rgba(255,0,85,0.2); }
    .glow-wait { color: #333; }

    /* --- STATUS ROW --- */
    .info-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-bottom: 40px; }
    .info-box { background: var(--card-bg); border: 1px solid #1a1a1a; padding: 12px; text-align: center; border-radius: 4px; }
    .info-label { font-size: 0.6rem; color: var(--dim); text-transform: uppercase; margin-bottom: 5px; font-weight: bold; }
    .info-val { font-size: 0.9rem; font-weight: 700; color: #ddd; }

    /* --- HISTORY TABLE --- */
    .table-header { color: var(--dim); font-size: 0.75rem; letter-spacing: 1px; margin-bottom: 15px; font-weight: 700; }
    .history-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    .history-table th { text-align: left; color: #333; padding-bottom: 10px; font-size: 0.7rem; text-transform: uppercase; }
    .history-table td { padding: 12px 0; border-bottom: 1px solid #1a1a1a; font-weight: 700; }
    .col-issue { color: var(--dim); }
    .col-level { font-size: 0.7rem; letter-spacing: 1px; }
    .col-res { text-align: right; }
    
    .res-win { color: var(--green); }
    .res-loss { color: var(--red); }
    .level-ghost { color: var(--purple); }
    .level-real { color: #fff; opacity: 0.5; }

    /* Utility */
    .hidden { display: none; }
    
</style>
</head>
<body>

<div class="container">
    
    <div class="stats-row">
        <div class="stat-box">
            <div class="stat-label">Real W Streak</div>
            <div class="stat-val text-green" id="w-streak">0</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Real L Streak</div>
            <div class="stat-val text-red" id="l-streak">0</div>
        </div>
        
        <div class="stat-box">
            <div class="stat-label">Total Real Wins</div>
            <div class="stat-val text-white" id="total-win">0</div>
        </div>
        <div class="stat-box">
            <div class="stat-label">Total Real Loss</div>
            <div class="stat-val text-white" id="total-loss">0</div>
        </div>
    </div>

    <div class="pred-section">
        <div class="period-label">PERIOD: <span id="period">Loading...</span></div>
        <div class="main-pred glow-wait" id="prediction">---</div>
    </div>

    <div class="info-row">
        <div class="info-box">
            <div class="info-label">Status</div>
            <div class="info-val" id="status-text">SYNC</div>
        </div>
        <div class="info-box">
            <div class="info-label">Timer</div>
            <div class="info-val" id="timer">--s</div>
        </div>
        <div class="info-box">
            <div class="info-label">Level</div>
            <div class="info-val" id="level">---</div>
        </div>
    </div>

    <div class="table-header">RECENT TRAJECTORY</div>
    <table class="history-table">
        <thead>
            <tr>
                <th style="width:20%">ISSUE</th>
                <th style="width:20%">PRED</th>
                <th style="width:40%">LEVEL</th>
                <th style="width:20%; text-align:right">RES</th>
            </tr>
        </thead>
        <tbody id="history-body">
            </tbody>
    </table>

</div>

<script>
    function calculateStats(history) {
        let realWins = 0, realLosses = 0;
        let wStreak = 0, lStreak = 0;
        let streakActive = true;

        history.forEach(row => {
            if(row.level === 'GHOST_SIM') return; // Strictly ignore ghosts

            // Total Counters
            if(row.result === 'WIN') realWins++;
            if(row.result === 'LOSS') realLosses++;

            // Streak Logic (Top Down)
            if(streakActive) {
                if(row.result === 'WIN') {
                    if(lStreak > 0) streakActive = false; 
                    else wStreak++;
                } else if(row.result === 'LOSS') {
                    if(wStreak > 0) streakActive = false;
                    else lStreak++;
                }
            }
        });
        return { wStreak, lStreak, realWins, realLosses };
    }

    async function update() {
        try {
            let res = await fetch('/data');
            let data = await res.json();
            
            // 1. Period & Prediction
            document.getElementById('period').innerText = data.period || '---';
            const predEl = document.getElementById('prediction');
            const p = data.prediction || '---';
            predEl.innerText = p;

            // Colorize Giant Text
            predEl.className = 'main-pred';
            if(p === 'BIG' || p === 'GREEN') predEl.classList.add('glow-green');
            else if(p === 'SMALL' || p === 'RED') predEl.classList.add('glow-red');
            else predEl.classList.add('glow-wait');

            // 2. Info Boxes
            document.getElementById('status-text').innerText = (data.status_text || 'ACTIVE').replace('SYNC ', '');
            document.getElementById('timer').innerText = (data.timer || 0) + 's';
            document.getElementById('level').innerText = data.level || '---';

            // 3. Stats (Real Only)
            const stats = calculateStats(data.history || []);
            
            // Update Streaks
            document.getElementById('w-streak').innerText = stats.wStreak;
            document.getElementById('l-streak').innerText = stats.lStreak;
            
            // Update Totals
            document.getElementById('total-win').innerText = stats.realWins;
            document.getElementById('total-loss').innerText = stats.realLosses;

            // 4. Table Generation
            let html = '';
            (data.history || []).forEach(row => {
                let isGhost = row.level === 'GHOST_SIM';
                
                // Color Classes
                let resClass = row.result === 'WIN' ? 'res-win' : (row.result === 'LOSS' ? 'res-loss' : '');
                let levelClass = isGhost ? 'level-ghost' : 'level-real';
                
                html += `
                <tr>
                    <td class="col-issue">${row.period.slice(-4)}</td>
                    <td style="font-weight:800">${row.pred}</td>
                    <td class="${levelClass}">${row.level}</td>
                    <td class="col-res ${resClass}">${row.result}</td>
                </tr>`;
            });
            document.getElementById('history-body').innerHTML = html;

        } catch(e) { console.log(e); }
    }
    
    setInterval(update, 1000);
    update();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
