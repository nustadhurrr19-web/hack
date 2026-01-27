# ==============================================================================
# MODULE: FETCHER.PY (V2026.99 - INSTANT BOOT FIX)
# ==============================================================================

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
    from prediction_engine import get_tricore_prediction, get_outcome
    print("[INIT] TRI-CORE ARCHITECT ENGINE LOADED.")
except ImportError as e:
    print(f"\n[CRITICAL ERROR] prediction_engine.py error: {e}")
    sys.exit()

# --- CONFIGURATION ---
API_URL = "https://api-iok6.onrender.com/api/get_history"
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
HISTORY_LIMIT = 2000       
MIN_DATA_REQUIRED = 10  
DB_FILE = 'ar_lottery_history.db'
DASHBOARD_FILE = 'dashboard_data.json'

RAM_HISTORY = deque(maxlen=HISTORY_LIMIT)
UI_HISTORY = deque(maxlen=20) 
VIRTUAL_PERFORMANCE = deque(maxlen=10) 

# --- STATE VARIABLES ---
last_processed_issue = None
stats = {"wins": 0, "losses": 0}
current_mode = "GHOST"

# [NEW] ADVANCED LOGIC STATE
consecutive_losses = 0
wins_accumulated = 0       # Tracks wins since last cooldown
cooldown_remaining = 0     # How many bets to stay in Ghost mode

# --- DASHBOARD SYNC ---
def update_dashboard(period="---", pred="WAITING", level="---", status="IDLE", timer="--", engine_data=None):
    if len(VIRTUAL_PERFORMANCE) > 0:
        v_wins = sum(VIRTUAL_PERFORMANCE)
        logic_health = int((v_wins / len(VIRTUAL_PERFORMANCE)) * 100)
    else:
        logic_health = 100 

    data = {
        "period": str(period),
        "prediction": pred,
        "level": level,
        "timer": timer,
        "status_text": status,
        "mode": current_mode, 
        "logic_health": f"{logic_health}%",
        "engines": engine_data or {"fractal": "-", "momentum": "-", "ml": "-"},
        "stats": {
            "wins": stats['wins'],
            "losses": stats['losses'],
            "streak_loss": consecutive_losses,
            "cooldown_rem": cooldown_remaining
        },
        "history": list(UI_HISTORY)
    }
    try:
        with open(DASHBOARD_FILE, 'w') as f:
            json.dump(data, f)
    except: pass

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
        print(f"   [DB] Loaded {len(RAM_HISTORY)} records from local database.")
    except: pass

async def fetch_api_data(session, size=20):
    try:
        params = {"size": size, "pageSize": size, "limit": size, "pageNo": 1}
        async with session.get(API_URL, headers=HEADERS, params=params, timeout=10) as response:
            if response.status == 200:
                json_data = await response.json(content_type=None)
                return json_data.get('data', {}).get('list', []) or json_data.get('list', [])
    except: pass
    return None

async def main_loop():
    global last_processed_issue, current_mode, consecutive_losses, wins_accumulated, cooldown_remaining
    
    ensure_db_setup()
    update_dashboard(status="BOOTING...", timer="INIT")
    
    pending_bet = {'issue': None, 'pred': None, 'mode_at_bet': 'GHOST'}
    
    async with aiohttp.ClientSession() as session:
        print("\n" + "="*50)
        print("   TITAN ARCHITECT // GHOST + STRICT PROTOCOL")
        print("   [!] Booting Up... Fetching History...")
        print("="*50)
        
        await load_db_to_ram()

        print("   [API] Fetching last 200 rounds to sync logic...")
        boot_data = await fetch_api_data(session, size=200)
        if boot_data:
            print(f"   [API] Success. Processing {len(boot_data)} records...")
            for item in reversed(boot_data):
                i_iss = str(item.get('issueNumber') or item.get('issue'))
                i_num = int(item.get('number') or item.get('result'))
                await save_to_db(i_iss, i_num)
                if not any(d['issue'] == i_iss for d in RAM_HISTORY):
                    RAM_HISTORY.append({'issue': i_iss, 'actual_number': i_num})
            print(f"   [SYSTEM] History Synced. Total RAM: {len(RAM_HISTORY)}")
        else:
            print("   [WARN] Boot fetch failed. Starting with empty/local data.")

        print("   [SYSTEM] Starting Live Monitoring...")

        while True:
            sec_remaining = 60 - datetime.now().second
            timer_display = f"{sec_remaining}"
            
            raw_list = await fetch_api_data(session, size=20)
            
            if raw_list:
                latest = raw_list[0]
                curr_issue = str(latest.get('issueNumber') or latest.get('issue'))
                curr_num = int(latest.get('number') or latest.get('result'))
                
                for item in reversed(raw_list):
                    i_iss = str(item.get('issueNumber') or item.get('issue'))
                    i_num = int(item.get('number') or item.get('result'))
                    if not any(d['issue'] == i_iss for d in RAM_HISTORY):
                        RAM_HISTORY.append({'issue': i_iss, 'actual_number': i_num})

                # --- NEW RESULT DETECTED ---
                if curr_issue != last_processed_issue:
                    actual_outcome = get_outcome(curr_num)
                    
                    if last_processed_issue:
                        print(f"\n[RESULT] {curr_issue} | {curr_num} ({actual_outcome})")

                    # 1. Grade Previous Bet
                    if pending_bet['issue'] == curr_issue and pending_bet['pred'] is not None:
                        did_win = (pending_bet['pred'] == actual_outcome)
                        VIRTUAL_PERFORMANCE.append(1 if did_win else 0)
                        
                        # LOGIC UPDATES
                        if did_win:
                            consecutive_losses = 0
                            wins_accumulated += 1 # Add to cooldown counter
                            res_display = "WIN"
                            if pending_bet['mode_at_bet'] == 'REAL': stats['wins'] += 1
                        else:
                            consecutive_losses += 1
                            # wins_accumulated does not reset on loss, only on cooldown trigger? 
                            # Usually win streaks are consecutive. Assuming cumulative based on "after 10 wins"
                            # If you want STRICT CONSECUTIVE wins, uncomment line below:
                            # wins_accumulated = 0 
                            res_display = "LOSS"
                            if pending_bet['mode_at_bet'] == 'REAL': stats['losses'] += 1

                        print(f"   >>> {res_display} (Streak Loss: {consecutive_losses}) <<<")
                        
                        UI_HISTORY.appendleft({
                            "period": curr_issue,
                            "pred": pending_bet['pred'],
                            "result": res_display,
                            "mode": pending_bet['mode_at_bet']
                        })
                    
                    # 2. CHECK COOLDOWN TRIGGER
                    if wins_accumulated >= 10:
                        print(f"   [!] 10 WINS REACHED -> ACTIVATING 10 ROUND COOLDOWN")
                        cooldown_remaining = 10
                        wins_accumulated = 0 # Reset counter
                    
                    if cooldown_remaining > 0:
                        cooldown_remaining -= 1
                        print(f"   [i] Cooldown Active. Remaining: {cooldown_remaining}")

                    # 3. DECIDE MODE
                    health_score = 0
                    if len(VIRTUAL_PERFORMANCE) > 0:
                        health_score = sum(VIRTUAL_PERFORMANCE) / len(VIRTUAL_PERFORMANCE)
                    
                    # Force Ghost if Cooldown
                    if cooldown_remaining > 0:
                        current_mode = "GHOST (COOLDOWN)"
                    else:
                        # Standard Switching Logic
                        if health_score >= 0.65:
                            current_mode = "REAL"
                        elif health_score <= 0.40:
                            current_mode = "GHOST"

                    # 4. GET NEXT PREDICTION
                    if len(RAM_HISTORY) >= MIN_DATA_REQUIRED:
                        next_issue = str(int(curr_issue) + 1)
                        
                        # CHECK FOR STRICT RECOVERY (2+ LOSSES)
                        strict_trigger = (consecutive_losses >= 2)
                        
                        res = get_tricore_prediction(list(RAM_HISTORY), strict_recovery=strict_trigger)
                        
                        decision = res['decision']
                        reason = res['reason']
                        eng_details = res['details']
                        
                        if strict_trigger:
                             reason = "[STRICT] " + reason

                        if decision == "SKIP":
                            print(f"[PRED] {next_issue} | SKIP | {reason}")
                            pending_bet = {'issue': next_issue, 'pred': None, 'mode_at_bet': current_mode}
                            update_dashboard(period=next_issue, pred="SKIP", status="WAITING", timer=timer_display, engine_data=eng_details)
                        else:
                            print(f"[PRED] {next_issue} | {decision} | {current_mode} | {reason}")
                            pending_bet = {'issue': next_issue, 'pred': decision, 'mode_at_bet': current_mode}
                            update_dashboard(period=next_issue, pred=decision, level=current_mode, status="ACTIVE (" + reason + ")", timer=timer_display, engine_data=eng_details)

                    last_processed_issue = curr_issue
            
            await asyncio.sleep(1)
            if pending_bet['issue']:
                 update_dashboard(period=pending_bet['issue'], pred=pending_bet['pred'] or "SKIP", level=current_mode, status="SCANNING..." if not pending_bet['pred'] else "WAITING", timer=timer_display)

if __name__ == '__main__':
    try: asyncio.run(main_loop())
    except KeyboardInterrupt: print("\n[EXIT] Stopped.")
