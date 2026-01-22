# run_bot.py
# Real-Time Prediction Bot using 11k API & Your Prediction Engine

import requests
import time
import sqlite3
import json
from datetime import datetime
from database_handler import save_result_to_database, ensure_setup

# Import your existing engine
try:
    from prediction_engine import ultraAIPredict, get_big_small_from_number
except ImportError:
    print("[ERROR] prediction_engine.py not found. Make sure it is in the same folder.")
    exit()

# --- CONFIGURATION ---
API_URL = "https://harshpredictor.site/api/api.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Connection": "keep-alive"
}
POLL_INTERVAL = 5  # Check for new results every 5 seconds

# --- DATABASE HELPERS ---
def get_recent_history(limit=2000):
    """Loads history from DB formatted for the prediction engine."""
    conn = sqlite3.connect('ar_lottery_history.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # We need the columns: issue, actual_number, actual_outcome
    cursor.execute("SELECT issue, code FROM results ORDER BY issue DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    # Engine expects oldest -> newest, so we reverse the DB fetch
    for r in reversed(rows):
        try:
            code_str = str(r['code'])
            num = int(code_str[-1]) # Last digit
            outcome = get_big_small_from_number(num)
            
            history.append({
                'issue': str(r['issue']),
                'actual_number': num,
                'actual_outcome': outcome
            })
        except:
            continue
            
    return history

# --- API FETCHING ---
def fetch_latest_data():
    try:
        resp = requests.get(API_URL, headers=HEADERS, params={'pageSize': 10, 'page': 1}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        # Handle nested data structure
        raw_list = []
        if isinstance(data, dict) and 'data' in data:
            raw_list = data['data']
            if isinstance(raw_list, dict) and 'list' in raw_list:
                raw_list = raw_list['list']
        elif isinstance(data, list):
            raw_list = data
            
        normalized = []
        for item in raw_list:
            # Flexible key search
            issue = item.get('issueNumber') or item.get('period') or item.get('issue')
            code = item.get('number') or item.get('result') or item.get('openNumber')
            
            if issue and code is not None:
                normalized.append({
                    'issue': str(issue),
                    'code': int(code),
                    'api_timestamp': str(datetime.now()),
                    'fetch_timestamp': time.time()
                })
        
        # Sort old -> new
        normalized.sort(key=lambda x: x['issue'])
        return normalized
        
    except Exception as e:
        print(f"[API ERROR] {e}")
        return []

# --- MAIN LOOP ---
async def main_loop():
    ensure_setup()
    print("------------------------------------------------")
    print("   MR.PERFECT V5 - REAL TIME AUTO-PREDICTOR")
    print("   Connected to: harshpredictor.site")
    print("------------------------------------------------\n")
    
    last_processed_issue = None
    
    while True:
        # 1. Fetch Data
        new_data = fetch_latest_data()
        
        if new_data:
            # Save to DB
            await save_result_to_database(new_data)
            
            latest_issue = new_data[-1]['issue']
            latest_result = new_data[-1]['code']
            
            # 2. Check if we have a new period
            if latest_issue != last_processed_issue:
                print(f"\n[NEW RESULT] Period: {latest_issue} | Result: {latest_result}")
                
                # 3. Load History & Predict
                history = get_recent_history(limit=500) # Use 500 rows for engine context
                
                if len(history) > 10:
                    # Run the Engine
                    prediction_data = ultraAIPredict(history)
                    
                    # Extract Key Info
                    pred_label = prediction_data.get('finalDecision', 'N/A')
                    confidence = prediction_data.get('finalConfidence', 0.0) * 100
                    next_period = int(latest_issue) + 1
                    
                    # 4. Display Output
                    print(f"========================================")
                    print(f"PREDICTION FOR PERIOD: {next_period}")
                    print(f"Outcome    : {pred_label}")
                    print(f"Confidence : {confidence:.1f}%")
                    print(f"Logic      : {prediction_data.get('source', 'Unknown')}")
                    print(f"========================================")
                else:
                    print("[WAITING] Not enough history to predict yet...")
                
                last_processed_issue = latest_issue
            else:
                # Waiting dots...
                print(".", end="", flush=True)
        
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\n[STOPPED] Bot stopped by user.")