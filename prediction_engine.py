# ==============================================================================
# MODULE: PREDICTION_ENGINE.PY (V2026.100 - SNIPER EDITION)
# ==============================================================================
import statistics
import random
import warnings
import math
import numpy as np
from collections import Counter

warnings.filterwarnings("ignore")

# --- ML IMPORTS ---
try:
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("[WARN] ML libraries missing. Running in 'Pattern+Math' mode.")

# --- UTILS ---
def get_outcome(n):
    """Converts number to BIG/SMALL outcome."""
    try:
        val = int(float(n))
        return "SMALL" if 0 <= val <= 4 else "BIG"
    except: return "UNKNOWN"

# =============================================================================
# PHASE 1: THE FOUNDATION (HURST EXPONENT)
# =============================================================================
def calculate_hurst(history, max_lag=20):
    try:
        # [SNIPER TWEAK] Fast-start with default TREND assumption if low data
        if len(history) < 10: return 0.6 
        
        data = [float(d['actual_number']) for d in history]
        available_lag = min(max_lag, len(data) // 2)
        if available_lag < 2: return 0.6
        
        lags = range(2, available_lag)
        tau = [np.sqrt(np.std(np.subtract(data[lag:], data[:-lag]))) for lag in lags]
        
        y = np.log(tau)
        x = np.log(lags)
        H = np.polyfit(x, y, 1)[0]
        return H
    except: return 0.6

# =============================================================================
# PHASE 2: THE 3 ENGINES (THE VOTERS)
# =============================================================================

# --- ENGINE 1: FRACTAL (Pattern) ---
def engine_fractal(history):
    try:
        if len(history) < 10: return None
        outcomes = "".join(["B" if get_outcome(d['actual_number']) == "BIG" else "S" for d in history])
        
        pattern = outcomes[-4:] # Short pattern for speed
        search_space = outcomes[:-1]
        
        found_count = search_space.count(pattern)
        if found_count < 2: return None
        
        next_b = 0
        start_idx = 0
        while True:
            idx = search_space.find(pattern, start_idx)
            if idx == -1: break
            if idx + 4 < len(search_space):
                if search_space[idx+4] == 'B': next_b += 1
            start_idx = idx + 1
            
        prob_big = next_b / found_count
        
        # [SNIPER TWEAK] Stricter pattern requirements
        if prob_big > 0.65: return {"vote": "BIG", "conf": prob_big}
        if prob_big < 0.35: return {"vote": "SMALL", "conf": 1.0 - prob_big}
    except: pass
    return None

# --- ENGINE 2: MOMENTUM (Physics) ---
def engine_momentum(history, market_phase="NEUTRAL"):
    try:
        if len(history) < 10: return None
        outcomes = [get_outcome(d['actual_number']) for d in history[-20:]]
        
        last_val = outcomes[-1]
        streak = 1
        for i in range(len(outcomes)-2, -1, -1):
            if outcomes[i] == last_val: streak += 1
            else: break
            
        if market_phase == "TREND":
            if streak >= 3: return {"vote": last_val, "conf": 0.75} # Strong Trend
        elif market_phase == "CHOP":
            if streak >= 2: return {"vote": "BIG" if last_val=="SMALL" else "SMALL", "conf": 0.65} # Fade
            
        recent = outcomes[-12:]
        big_count = recent.count("BIG")
        if big_count >= 8: return {"vote": "BIG", "conf": 0.70}
        if big_count <= 4: return {"vote": "SMALL", "conf": 0.70}
    except: pass
    return None

# --- ENGINE 3: SMART ML (The Brain) ---
class SmartML:
    def __init__(self):
        self.model = None
        self.is_trained = False
        self.last_train_size = 0

    def train(self, history):
        if not ML_AVAILABLE or len(history) < 30: return
        if self.is_trained and len(history) - self.last_train_size < 50: return

        try:
            df = pd.DataFrame(history)
            df['val'] = df['actual_number'].astype(int)
            df['target'] = df['val'].apply(lambda x: 1 if x >= 5 else 0).shift(-1)
            df['ma_5'] = df['val'].rolling(5).mean()
            df['ma_10'] = df['val'].rolling(10).mean()
            df = df.dropna()
            
            X = df[['ma_5', 'ma_10']]
            y = df['target']
            
            self.model = RandomForestClassifier(n_estimators=50, max_depth=5)
            self.model.fit(X, y)
            self.is_trained = True
            self.last_train_size = len(history)
        except: pass

    def predict(self, history):
        if not self.is_trained: return None
        try:
            subset = history[-15:]
            df = pd.DataFrame(subset)
            df['val'] = df['actual_number'].astype(int)
            ma5 = df['val'].rolling(5).mean().iloc[-1]
            ma10 = df['val'].rolling(10).mean().iloc[-1]
            
            prob_big = self.model.predict_proba([[ma5, ma10]])[0][1]
            vote = "BIG" if prob_big > 0.5 else "SMALL"
            conf = prob_big if vote == "BIG" else 1 - prob_big
            
            # [SNIPER TWEAK] Higher ML confidence needed
            if conf > 0.55: return {"vote": vote, "conf": conf}
        except: pass
        return None

brain = SmartML()

# =============================================================================
# PHASE 3: CONSENSUS FILTER (THE SNIPER)
# =============================================================================
def get_tricore_prediction(history):
    
    hurst = calculate_hurst(history)
    
    market_phase = "NEUTRAL"
    if hurst > 0.6: market_phase = "TREND"
    elif hurst < 0.4: market_phase = "CHOP"
    
    # [SNIPER TWEAK] Strict Chaos Filter
    if 0.48 < hurst < 0.52:
        return {
            "decision": "SKIP", 
            "reason": f"CHAOS (H={hurst:.2f})",
            "details": {"fractal": "-", "momentum": "-", "ml": "-"}
        }

    brain.train(history)
    votes = []
    engine_details = {"fractal": "-", "momentum": "-", "ml": "-"}
    
    v1 = engine_fractal(history)
    if v1: 
        votes.append(v1)
        engine_details['fractal'] = f"{v1['vote']} ({int(v1['conf']*100)}%)"
        
    v2 = engine_momentum(history, market_phase)
    if v2: 
        votes.append(v2)
        engine_details['momentum'] = f"{v2['vote']} ({int(v2['conf']*100)}%)"
        
    v3 = brain.predict(history)
    if v3: 
        votes.append(v3)
        engine_details['ml'] = f"{v3['vote']} ({int(v3['conf']*100)}%)"
    
    if not votes:
        return {"decision": "SKIP", "reason": "SILENCE", "details": engine_details}
        
    big_votes = sum(1 for v in votes if v['vote'] == "BIG")
    small_votes = sum(1 for v in votes if v['vote'] == "SMALL")
    
    final_decision = "SKIP"
    reason = "CONFLICT"
    
    # [SNIPER TWEAK] Strict Voting Logic
    if big_votes >= 2:
        final_decision = "BIG"
        reason = f"SNIPER ({big_votes}/3)"
    elif small_votes >= 2:
        final_decision = "SMALL"
        reason = f"SNIPER ({small_votes}/3)"
    elif len(votes) == 1:
        solo = votes[0]
        # Only accept Solo bets if SUPER High Confidence
        if solo['conf'] > 0.75:
            final_decision = solo['vote']
            reason = f"GOLDEN SOLO ({int(solo['conf']*100)}%)"
            
    return {
        "decision": final_decision,
        "reason": reason,
        "details": engine_details
    }
