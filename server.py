from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for
import sqlite3, os, json, functools, uuid, hmac, hashlib, base64
import threading, asyncio
from datetime import datetime, timedelta
import encodings.idna  # Render fix

import fetcher  # DO NOT TOUCH

app = Flask(__name__)

# ===================== SECURITY CONFIG =====================
app.secret_key = "TITAN_SECURE_KEY_CHANGE_THIS"
ADMIN_PASSWORD = "admin"
OFFLINE_SECRET = "TITAN_OFFLINE_SECRET_CODE_123"
MASTER_KEY = "TITAN-PERM-ADMIN"

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
    c.execute("""CREATE TABLE IF NOT EXISTS active_sessions (
        session_id TEXT PRIMARY KEY,
        key_code TEXT,
        last_seen TIMESTAMP,
        ip_address TEXT
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
    if key == MASTER_KEY:
        return True, {"name": "ADMIN", "expires": datetime.max}

    if not key.startswith("TITAN-"):
        return False, "Invalid Key"

    try:
        _, payload, sig = key.split('-')
        payload += '=' * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(payload).decode()
        ts, _, name = raw.split('|')
        calc = hmac.new(OFFLINE_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:8].upper()
        if calc != sig:
            return False, "Invalid Signature"
        if datetime.now() > datetime.fromtimestamp(int(ts)):
            return False, "Key Expired"
        return True, {"name": name, "expires": datetime.fromtimestamp(int(ts))}
    except:
        return False, "Corrupt Key"

def login_required(f):
    @functools.wraps(f)
    def wrap(*a, **k):
        if not session.get("auth"):
            return redirect(url_for("login"))
        return f(*a, **k)
    return wrap

# ===================== ROUTES =====================
@app.route("/login", methods=["GET", "POST"])
def login():
    err = None
    if request.method == "POST":
        key = request.form.get("key")
        dev = request.form.get("device")
        c = db()

        if c.execute("SELECT 1 FROM blacklisted_keys WHERE key_code=?", (key,)).fetchone():
            err = "KEY BANNED"
        else:
            row = c.execute("SELECT * FROM access_keys WHERE key_code=?", (key,)).fetchone()
            if not row:
                ok, res = validate_offline_key(key)
                if not ok:
                    err = res
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
    <body style="background:black;color:#0f0;display:flex;justify-content:center;align-items:center;height:100vh;font-family:monospace">
    <form method="post">
    <h2>TITAN ACCESS</h2>
    <p style="color:red">{err or ''}</p>
    <input type="hidden" name="device" id="d">
    <input name="key" placeholder="PASTE KEY" style="padding:10px"><br><br>
    <button>LOGIN</button>
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

@app.route("/heartbeat", methods=["POST"])
def hb():
    return "ok"

@app.route("/data")
@login_required
def data():
    try:
        return jsonify(json.load(open(DASHBOARD_FILE)))
    except:
        return jsonify({})

@app.route("/")
@login_required
def index():
    return render_template_string(HTML)

# ===================== NEW UI =====================
HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>TITAN V700</title>
<style>
body{background:#050505;color:#fff;font-family:Inter;margin:0}
.card{background:#111;border:1px solid #222;border-radius:12px;padding:14px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
.green{color:#00ff41}.red{color:#ff0055}.purple{color:#c77dff}
</style>
</head>
<body>
<div class=card>
<b id=pred style="font-size:48px">---</b>
<div id=level></div>
<div id=timer></div>
</div>

<div class="card grid">
<div>REAL W<br><b class=green id=rw>0</b></div>
<div>REAL L<br><b class=red id=rl>0</b></div>
<div>GHOST W<br><b class=purple id=gw>0</b></div>
<div>GHOST L<br><b class=purple id=gl>0</b></div>
</div>

<div class=card id=hist></div>

<script>
async function u(){
 let d=await fetch('/data').then(r=>r.json())
 document.getElementById('pred').innerText=d.prediction||'---'
 document.getElementById('level').innerText=d.level||''
 document.getElementById('timer').innerText=d.timer||''
 let rw=0,rl=0,gw=0,gl=0,h=''
 ;(d.history||[]).forEach(x=>{
   if(x.level==='GHOST_SIM'){
     x.result==='WIN'?gw++:gl++
   }else{
     x.result==='WIN'?rw++:rl++
   }
   h+=`<div>${x.period} ${x.pred} ${x.result} ${x.level}</div>`
 })
 rw&&(document.getElementById('rw').innerText=rw)
 rl&&(document.getElementById('rl').innerText=rl)
 gw&&(document.getElementById('gw').innerText=gw)
 gl&&(document.getElementById('gl').innerText=gl)
 document.getElementById('hist').innerHTML=h
}
setInterval(u,1000);u()
</script>
</body>
</html>
"""

# ===================== RUN =====================
if __name__ == "__main__":
    app.run()
