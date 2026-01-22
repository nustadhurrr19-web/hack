
import sys
import sqlite3, json, os, sys
from prediction_engine import ultraAIPredict, get_big_small_from_number
from datetime import datetime

DB = "ar_lottery_history.db"

def ensure_predictions_table(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        predict_for_issue TEXT,
        predicted_label TEXT,
        confidence REAL,
        engine_details TEXT,
        predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()

def extract_number_from_code(code):
    if code is None:
        return None
    s = str(code)
    parts = [p for p in s.replace('\\n','').split(',') if any(ch.isdigit() for ch in p)]
    if not parts:
        digits = ''.join(ch for ch in s if ch.isdigit())
        if not digits: return None
        return int(digits[-1])
    last = parts[-1].strip()
    digits = ''.join(ch for ch in last if ch.isdigit())
    if not digits: return None
    return int(digits[-1])

def load_history():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    # get columns
    cur.execute("PRAGMA table_info(results)")
    cols = [r[1] for r in cur.fetchall()]
    cur.execute("SELECT * FROM results ORDER BY rowid ASC")
    rows = cur.fetchall()
    conn.close()
    history = []
    for r in rows:
        rowd = dict(zip(cols, r))
        entry = {}
        entry['id'] = rowd.get('id') or rowd.get('rowid') or None
        entry['issue'] = rowd.get('issue') or rowd.get('issue_no') or rowd.get('issueNumber') or rowd.get('issue_id') or rowd.get('issueCode') or ''
        entry['code'] = rowd.get('code') or rowd.get('value') or rowd.get('numbers') or ''
        entry['api_timestamp'] = rowd.get('api_timestamp') or rowd.get('timestamp') or None
        entry['fetch_timestamp'] = rowd.get('fetch_timestamp') or rowd.get('fetched_at') or None
        num = extract_number_from_code(entry['code'])
        entry['actual_number'] = num
        entry['actual_outcome'] = get_big_small_from_number(num)
        history.append(entry)
    return history

def pretty_print_line(idx, issue, pred, conf, actual, result, win_streak, loss_streak):
    print(f"{idx:4d} | Issue:{issue} | Pred:{pred:5s} | Conf:{conf:.2f} | Actual:{actual:5s} | Result:{result:4s} | WinStreak:{win_streak} | LossStreak:{loss_streak}")

def run_backtest():
    history = load_history()
    if len(history) < 5:
        print("Not enough history to backtest.")
        return
    conn = sqlite3.connect(DB)
    ensure_predictions_table(conn)
    win_streak = 0
    loss_streak = 0
    total = 0
    correct = 0
    for t in range(5, len(history)):
        past = history[:t]  # oldest first
        past_for_engine = list(reversed(past))
        try:
            out = ultraAIPredict(past_for_engine, None)
        except Exception as e:
            print("Engine error for t=", t, "err:", e)
            continue
        predicted = out.get('finalDecision') or out.get('lastPredictedOutcome') or out.get('finalDecision') or 'N/A'
        conf = out.get('finalConfidence') or out.get('lastFinalConfidence') or 0.5
        actual = history[t]['actual_outcome'] or 'N/A'
        issue = history[t]['issue'] or history[t]['id']
        result = 'N/A'
        if predicted in ['BIG','SMALL'] and actual in ['BIG','SMALL']:
            total += 1
            if predicted == actual:
                result = 'WIN'
                correct += 1
                win_streak += 1
                loss_streak = 0
            else:
                result = 'LOSS'
                loss_streak += 1
                win_streak = 0
        pretty_print_line(t, issue, predicted, conf, actual, result, win_streak, loss_streak)
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO predictions (predict_for_issue, predicted_label, confidence, engine_details) VALUES (?, ?, ?, ?)", 
                        (str(issue), predicted, float(conf), json.dumps(out)))
            conn.commit()
        except Exception as e:
            print("DB save error:", e)
    conn.close()
    if total>0:
        print("Backtest summary: Total:", total, "Correct:", correct, "Accuracy:", correct/total)
    else:
        print("No valid predictions compared during backtest.")

if __name__ == '__main__':
    run_backtest()


# --- AUTO-ADDED: calibration & backtest commands ---
def cli_calibrate_patterns(history_json='history_records.json', out_path='pattern_stats.json'):
    from calibrate_patterns import calibrate, load_history_json
    import os
    if not os.path.exists(history_json):
        print('history_records.json not found. create it with fields detected_patterns, next_results, predicted_label(optional).')
        return
    recs = load_history_json(history_json)
    pattern_names = set()
    for r in recs:
        for p in r.get('detected_patterns', []):
            pattern_names.add(p)
    stats = calibrate(pattern_names, recs, k=3, out_path=out_path)
    print('Calibrated patterns saved to', out_path)

def cli_sweep_backtest(configs=None, out_path='backtest_sweep.json'):
    \"\"\"Run systematic backtests sweeping P_win_3 thresholds and stake plans.
    Requires a backtester function or script that can accept configs. We'll call run_backtest if available.
    \"\"\"
    print('Starting simple sweep backtest (this is a thin orchestration wrapper).')
    # Simple default configs
    if configs is None:
        configs = []
        for thr in [0.55,0.6,0.65,0.7]:
            for plan in ['bet_level1','staged','hedge']:
                configs.append({'p_win_3_threshold':thr, 'plan':plan})
    results = []
    for cfg in configs:
        print('Simulating cfg', cfg)
        # placeholder: call existing backtest runner if present; otherwise record no-op
        results.append({'config':cfg, 'result': 'not_executed'})
    import json
    with open(out_path,'w',encoding='utf-8') as fh:
        json.dump(results, fh, indent=2)
    print('Saved sweep results to', out_path)

if __name__ == '__main__':
    import sys
    if len(sys.argv)>=2:
        cmd = sys.argv[1]
        if cmd == 'calibrate_patterns':
            cli_calibrate_patterns()
        elif cmd == 'sweep_backtest':
            cli_sweep_backtest()
        else:
            print('Unknown command. Supported: calibrate_patterns, sweep_backtest')
    else:
        print('No CLI command passed. To calibrate patterns: python run_predictions_cli.py calibrate_patterns')
