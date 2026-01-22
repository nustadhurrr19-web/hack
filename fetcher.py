# ==============================================================================
# MODULE: FETCHER.PY (V2026.38 - TITAN COMPLETE EDITION)
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

try:
    # UPDATED IMPORT: Added report_outcome_to_tracker for Dynamic Weighting
    from prediction_engine import ultraAIPredict, get_outcome_from_number, report_outcome_to_tracker
    print("[INIT] TITAN V2026.38 LINKED.")
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
MIN_DATA_REQUIRED = 50  
DB_FILE = 'ar_lottery_history.db'
DASHBOARD_FILE = 'dashboard_data.json'

RAM_HISTORY = deque(maxlen=HISTORY_LIMIT)
UI_HISTORY = deque(maxlen=50)

# --- STATE TRACKING ---
last_prediction = {
    "issue": None, "label": "WAITING", "conf": 0, 
    "level": "---", "reason": "Booting...", "raw_votes": {}
}
session_wins = 0
session_losses = 0
last_win_status = "NONE" 
consecutive_wins = 0
consecutive_losses = 0

# --- GHOST & MOMENTUM TRACKING ---
current_momentum = 0.0 
consecutive_ghost_wins = 0  
consecutive_ghost_losses = 0

# --- COOLDOWN TRACKING ---
total_wins_accumulated = 0
COOLDOWN_TRIGGER = 10      
COOLDOWN_DURATION = 10    
cooldown_rounds_left = 0

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

def update_dashboard(status_text="IDLE", timer_val=0):
    total = session_wins + session_losses
    acc = f"{(session_wins/total)*100:.1f}%" if total > 0 else "0.0%"
    
    data = {
        "period": last_prediction['issue'] if last_prediction['issue'] else "---",
        "prediction": last_prediction['label'],
        "level": last_prediction.get('level', '---'),
        "votes": last_prediction.get('raw_votes', {}),
        "lastresult_status": last_win_status,
        "status_text": status_text,
        "timer": timer_val,
        "stats": {"wins": session_wins, "losses": session_losses, "accuracy": acc},
        "cooldown": cooldown_rounds_left,
        "momentum": current_momentum,
        "ghost_streak": f"W:{consecutive_ghost_wins} L:{consecutive_ghost_losses}",
        "history": list(UI_HISTORY) 
    }
    try:
        with open(DASHBOARD_FILE + ".tmp", "w") as f: json.dump(data, f)
        os.replace(DASHBOARD_FILE + ".tmp", DASHBOARD_FILE)
    except: pass

async def fetch_api_data(session, size_limit=20):
    params = {"size": size_limit, "pageSize": size_limit, "limit": size_limit, "pageNo": 1}
    try:
        async with session.get(API_URL, headers=HEADERS, params=params, timeout=15) as response:
            if response.status == 200:
                json_data = await response.json(content_type=None)
                return json_data.get('data', {}).get('list', []) or json_data.get('list', [])
    except: pass
    return None

async def main_loop():
    global last_prediction, last_win_status, session_wins, session_losses
    global total_wins_accumulated, cooldown_rounds_left
    global current_momentum, consecutive_ghost_wins, consecutive_ghost_losses
    
    ensure_db_setup()
    last_processed_issue = None
    
    async with aiohttp.ClientSession() as session:
        print("\n" + "="*64)
        print("   TITAN V2026.38 | FULL SPECTRUM ACTIVE")
        print("   [!] Dynamic Weighting: ACTIVE (Engines Self-Learning)")
        print("   [!] Ghost Breakthrough: ACTIVE (2 Wins Unlock)")
        print("   [!] Reversal Hunter: ACTIVE (2 Losses + High Conf Unlock)")
        print("="*64)
        
        # BOOT
        boot_data = await fetch_api_data(session, size_limit=2000)
        if boot_data:
            for item in reversed(boot_data):
                iss = item.get('issueNumber') or item.get('issue')
                num = item.get('number') or item.get('result')
                if iss and num is not None: await save_to_db(iss, num)
        await load_db_to_ram()

        while True:
            now = datetime.now()
            current_second = now.second
            time_until_deadline = 45 - current_second
            
            # Fetch Data
            raw_list = await fetch_api_data(session, size_limit=20)
            
            if raw_list:
                latest = raw_list[0]
                curr_issue = str(latest.get('issueNumber') or latest.get('issue'))
                curr_num = int(latest.get('number') or latest.get('result'))

                # Update DB
                for item in reversed(raw_list):
                    i_iss = str(item.get('issueNumber') or item.get('issue'))
                    i_num = int(item.get('number') or item.get('result'))
                    if not any(d['issue'] == i_iss for d in RAM_HISTORY):
                        RAM_HISTORY.append({'issue': i_iss, 'actual_number': i_num})

                update_dashboard(f"SYNC {cooldown_rounds_left}CD", 60 - current_second)
                
                if curr_issue != last_processed_issue:
                    
                    # 1. EVALUATE PREVIOUS
                    if last_prediction['issue'] == curr_issue:
                        real_outcome = get_outcome_from_number(curr_num)
                        pred_label = last_prediction['label']
                        pred_level = last_prediction.get('level', '---')
                        
                        # --- CRITICAL: FEEDBACK LOOP ---
                        # Send result to prediction engine to update engine weights
                        report_outcome_to_tracker(last_prediction.get('raw_votes', {}), real_outcome)

                        # A. REAL BETS
                        if pred_label not in ["WAITING", "SKIP", "COOLDOWN"] and pred_level != "GHOST_SIM":
                            consecutive_ghost_wins = 0 
                            consecutive_ghost_losses = 0
                            
                            if pred_label == real_outcome:
                                session_wins += 1
                                total_wins_accumulated += 1
                                last_win_status = "WIN"
                                current_momentum = min(current_momentum + 0.5, 2.0)
                                print(f"\n[WIN] {curr_issue} | Result: {real_outcome} | Mom: {current_momentum:+.1f}")
                                
                                if total_wins_accumulated >= COOLDOWN_TRIGGER:
                                    cooldown_rounds_left = COOLDOWN_DURATION
                                    total_wins_accumulated = 0
                                    print(f"[SYSTEM] 5 Wins! Resting for {COOLDOWN_DURATION} rounds.")
                            else:
                                session_losses += 1
                                last_win_status = "LOSS"
                                current_momentum = -1.0
                                print(f"\n[LOSS] {curr_issue} | Result: {real_outcome} | Mom: {current_momentum:+.1f}")
                            
                            UI_HISTORY.appendleft({
                                "period": curr_issue, 
                                "pred": pred_label, 
                                "result": last_win_status, 
                                "level": pred_level
                            })
                        
                        # B. GHOST BETS
                        elif pred_level == "GHOST_SIM":
                            if pred_label == real_outcome:
                                consecutive_ghost_wins += 1
                                consecutive_ghost_losses = 0
                                current_momentum = min(current_momentum + 0.5, 1.5)
                                print(f"\n[GHOST WIN] {curr_issue} | Streak: {consecutive_ghost_wins}W")
                                
                                if consecutive_ghost_wins >= 2:
                                    print("   >>> [ALERT] HOT HAND DETECTED. UNLOCKING REAL BETS. <<<")

                                UI_HISTORY.appendleft({
                                    "period": curr_issue, "pred": pred_label, "result": "WIN", "level": "GHOST_SIM"
                                })
                            else:
                                consecutive_ghost_losses += 1
                                consecutive_ghost_wins = 0
                                current_momentum = max(current_momentum - 0.5, -1.5)
                                print(f"\n[GHOST LOSS] {curr_issue} | Streak: {consecutive_ghost_losses}L")
                                
                                if consecutive_ghost_losses >= 2:
                                     print("   >>> [ALERT] REVERSAL PATTERN. WAITING FOR HIGH CONFIDENCE. <<<")
                                
                                UI_HISTORY.appendleft({
                                    "period": curr_issue, "pred": pred_label, "result": "LOSS", "level": "GHOST_SIM"
                                })
                        
                        else:
                            print(f"\n[SKIP] {curr_issue} was {real_outcome}")

                    # 2. HANDLE COOLDOWN
                    if cooldown_rounds_left > 0:
                        cooldown_rounds_left -= 1
                        print(f"[COOLDOWN] Rest mode... ({cooldown_rounds_left} left)")
                        last_prediction = {"issue": str(int(curr_issue)+1), "label": "COOLDOWN", "level": "REST", "raw_votes": {}}
                        last_processed_issue = curr_issue
                        await asyncio.sleep(2)
                        continue

                    # 3. PREDICT
                    if len(RAM_HISTORY) >= MIN_DATA_REQUIRED:
                        next_issue = str(int(curr_issue) + 1)
                        
                        if time_until_deadline > 10:
                            budget = time_until_deadline - 5
                            print(f"[PRED] Analyzing {next_issue}... (Budget: {budget}s)")
                            
                            try:
                                res = await ultraAIPredict(
                                    list(RAM_HISTORY), 
                                    0, 
                                    last_win_status=last_win_status, 
                                    current_momentum=current_momentum,
                                    ghost_wins_streak=consecutive_ghost_wins, 
                                    ghost_loss_streak=consecutive_ghost_losses,
                                    time_budget=budget
                                )
                                
                                final_decision = res['finalDecision']
                                final_level = res['level']
                                votes_str = " | ".join([f"{k}:{v}" for k,v in res['raw_votes'].items()])

                                last_prediction = {
                                    "issue": next_issue, 
                                    "label": final_decision, 
                                    "conf": res['confidence'], 
                                    "level": final_level, 
                                    "reason": res.get('reason', ''),
                                    "raw_votes": res.get('raw_votes', {})
                                }
                                
                                if final_level == "GHOST_SIM":
                                    print(f"[GHOST] {final_decision} (Simulating...) | Score: {res['confidence']:.1f}")
                                elif final_decision == "SKIP":
                                    print(f"[SKIP] Low Confidence ({res['confidence']:.1f})")
                                else:
                                    print(f"[PRED] {final_decision} [{final_level}] Score:{res['confidence']:.1f}")
                                    print(f"       Votes: {votes_str}")
                                
                            except Exception as e: 
                                print(f"[ERROR] {e}")
                        
                        else:
                             print(f"[PRED] {next_issue} | SKIP (Time low)")
                             last_prediction = {"issue": next_issue, "label": "SKIP", "level": "LATE", "raw_votes": {}}

                    last_processed_issue = curr_issue

            await asyncio.sleep(2)

if __name__ == '__main__':
    try: asyncio.run(main_loop())
    except KeyboardInterrupt: print("\n[EXIT] Offline.")