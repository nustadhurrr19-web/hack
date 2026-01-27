

import aiohttp
import asyncio
import json
import sqlite3
import time
import sys
import os
from collections import deque
from datetime import datetime

# --- IMPORT ENGINE ---
try:
    from prediction_engine import get_sniper_prediction, get_outcome
    print("[INIT] TITAN SNIPER LITE LOADED.")
except ImportError as e:
    print(f"\n[CRITICAL ERROR] prediction_engine.py not found: {e}")
    sys.exit()

# --- CONFIGURATION ---
API_URL = "https://api-iok6.onrender.com/api/get_history"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

HISTORY_LIMIT = 2000       
MIN_DATA_REQUIRED = 5  # Lowered for testing, set back to 50 if needed
DB_FILE = 'ar_lottery_history.db'
DASHBOARD_FILE = 'dashboard_data.json'

RAM_HISTORY = deque(maxlen=HISTORY_LIMIT)
UI_HISTORY = deque(maxlen=20) # Stores last 20 results for the dashboard

# --- STATE ---
last_processed_issue = None
recovery_mode = False 
consecutive_losses = 0
stats = {"wins": 0, "losses": 0}

# --- DASHBOARD SYNC FUNCTION ---
def update_dashboard(period="---", pred="WAITING", level="---", status="IDLE", timer="--"):
    """Writes the current state to dashboard_data.json for server.py to read."""
    
    # Calculate Accuracy
    total = stats['wins'] + stats['losses']
    acc = f"{(stats['wins']/total*100):.1f}%" if total > 0 else "0.0%"
    
    # Prepare Data Block
    data = {
        "period": str(period),
        "prediction": pred,
        "level": level,
        "timer": timer,
        "status_text": status,
        "stats": {
            "wins": stats['wins'],
            "losses": stats['losses'],
            "accuracy": acc
        },
        "history": list(UI_HISTORY) # Send the list as is (ordered)
    }
    
    # Atomic-like write
    try:
        with open(DASHBOARD_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[UI ERROR] Could not write dashboard data: {e}")

# --- DB FUNCTIONS ---
def ensure_db_setup():
    conn = sqlite3.connect(DB_FILE)
    conn.execute('CREATE TABLE IF NOT EXISTS results (issue TEXT PRIMARY KEY, code INTEGER, fetch_time TEXT)')
    conn.commit()
    conn.close()

async def save_to_db(issue, code):
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.execute("INSERT OR IGNORE INTO results (issue, code, fetch_time) VALUES (?, ?, ?)", 
                       (str(issue), int(code), str(datetime.now())))
        conn.commit()
        conn.close()
    except: pass

async def load_db_to_ram():
    RAM_HISTORY.clear()
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(f"SELECT issue, code FROM results ORDER BY issue DESC LIMIT {HISTORY_LIMIT}")
        rows = cursor.fetchall()
        conn.close()
        for r in reversed(rows):
            RAM_HISTORY.append({'issue': str(r[0]), 'actual_number': int(r[1])})
        return len(RAM_HISTORY)
    except: return 0

async def fetch_api_data(session, size_limit=20):
    params = {"size": size_limit, "pageSize": size_limit, "limit": size_limit, "pageNo": 1}
    try:
        async with session.get(API_URL, headers=HEADERS, params=params, timeout=5) as response:
            if response.status == 200:
                json_data = await response.json(content_type=None)
                return json_data.get('data', {}).get('list', []) or json_data.get('list', [])
    except: pass
    return None

async def main_loop():
    global last_processed_issue, recovery_mode, consecutive_losses
    
    ensure_db_setup()
    
    # Initial Dashboard Reset
    update_dashboard(status="BOOTING...", timer="INIT")
    
    pending_bet = {'issue': None, 'pred': None, 'is_virtual': False, 'level_name': '---'}
    
    async with aiohttp.ClientSession() as session:
        print("\n" + "="*50)
        print("   TITAN SNIPER // DASHBOARD CONNECTED")
        print("   [!] Logic: Detect New Result -> Update UI -> Predict")
        print("="*50)
        
        # Initial Load
        boot_data = await fetch_api_data(session, size_limit=2000)
        if boot_data:
            for item in reversed(boot_data):
                iss = item.get('issueNumber') or item.get('issue')
                num = item.get('number') or item.get('result')
                if iss and num is not None: await save_to_db(iss, num)
        await load_db_to_ram()

        while True:
            # Calculate simple countdown (approximate 60s cycle)
            sec_remaining = 60 - datetime.now().second
            timer_display = f"{sec_remaining}"
            
            # 1. Fetch Latest Data
            raw_list = await fetch_api_data(session, size_limit=20)
            
            if raw_list:
                latest = raw_list[0]
                curr_issue = str(latest.get('issueNumber') or latest.get('issue'))
                curr_num = int(latest.get('number') or latest.get('result'))
                
                # Update RAM
                for item in reversed(raw_list):
                    i_iss = str(item.get('issueNumber') or item.get('issue'))
                    i_num = int(item.get('number') or item.get('result'))
                    if not any(d['issue'] == i_iss for d in RAM_HISTORY):
                        RAM_HISTORY.append({'issue': i_iss, 'actual_number': i_num})

                # 2. TRIGGER: New Issue Detected?
                if curr_issue != last_processed_issue:
                    
                    actual_outcome = get_outcome(curr_num)
                    
                    if last_processed_issue:
                        print(f"\n[RESULT] {curr_issue} | {curr_num} ({actual_outcome})")

                    # --- GRADE PREVIOUS BET & UPDATE UI HISTORY ---
                    if pending_bet['issue'] == curr_issue and pending_bet['pred'] is not None:
                        did_win = (pending_bet['pred'] == actual_outcome)
                        mode_str = "VIRTUAL" if pending_bet['is_virtual'] else "REAL"
                        res_str = "WIN" if did_win else "LOSS"
                        
                        # Console Log
                        if did_win:
                            print(f"   >>> {mode_str} WIN <<<")
                            stats['wins'] += 1
                            recovery_mode = False
                        else:
                            print(f"   >>> {mode_str} LOSS <<<")
                            stats['losses'] += 1
                            if not pending_bet['is_virtual']:
                                recovery_mode = True
                                print("   [!] SHIELD ACTIVATED. SWAPPING TO VIRTUAL BETS.")
                        
                        # Add to UI History (Insert at top)
                        UI_HISTORY.appendleft({
                            "period": curr_issue,
                            "pred": pending_bet['pred'],
                            "level": pending_bet['level_name'],
                            "result": res_str
                        })

                    # --- INSTANT PREDICTION ---
                    if len(RAM_HISTORY) >= MIN_DATA_REQUIRED:
                        next_issue = str(int(curr_issue) + 1)
                        
                        # Update Dashboard to "CALCULATING"
                        update_dashboard(period=next_issue, status="CALCULATING...", timer=timer_display)
                        
                        # EXECUTE LOGIC
                        res = get_sniper_prediction(list(RAM_HISTORY))
                        decision = res['decision']
                        reason = res['reason']
                        
                        if decision == "SKIP":
                            print(f"[PRED] {next_issue} | SKIP | {reason}")
                            pending_bet = {'issue': next_issue, 'pred': None, 'is_virtual': False, 'level_name': 'SKIP'}
                            
                            # Update Dashboard (SKIP)
                            update_dashboard(
                                period=next_issue, 
                                pred="SKIP", 
                                level="---", 
                                status="WAITING FOR RESULT",
                                timer=timer_display
                            )
                            
                        else:
                            is_virtual_bet = recovery_mode
                            prefix = "[PRED]"
                            mode_tag = "(VIRTUAL)" if is_virtual_bet else "(REAL)"
                            level_name = "GHOST_SIM" if is_virtual_bet else "SAFE_BET"
                            
                            print(f"{prefix} {next_issue} | {decision} | {mode_tag} {reason}")
                            
                            pending_bet = {
                                'issue': next_issue, 
                                'pred': decision, 
                                'is_virtual': is_virtual_bet,
                                'level_name': level_name
                            }
                            
                            # Update Dashboard (ACTIVE BET)
                            update_dashboard(
                                period=next_issue, 
                                pred=decision, 
                                level=level_name, 
                                status="PREDICTION ACTIVE",
                                timer=timer_display
                            )

                    last_processed_issue = curr_issue
            
            # Heartbeat update for timer (even if no new result)
            if pending_bet['issue']:
                update_dashboard(
                    period=pending_bet['issue'],
                    pred=pending_bet['pred'] if pending_bet['pred'] else "SKIP",
                    level=pending_bet['level_name'],
                    status="SCANNING..." if not pending_bet['pred'] else "WAITING RESULT",
                    timer=timer_display
                )

            # Quick sleep
            await asyncio.sleep(1)

if __name__ == '__main__':
    try: asyncio.run(main_loop())
    except KeyboardInterrupt: print("\n[EXIT] Stopped.")
