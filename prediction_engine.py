
import statistics
import warnings
import numpy as np
from typing import Dict, List, Optional

warnings.filterwarnings("ignore")

# --- ML IMPORTS (FAIL-SAFE) ---
try:
    import pandas as pd
    from sklearn.ensemble import RandomForestClassifier
    import xgboost as xgb
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("[WARN] ML libraries (pandas/sklearn/xgboost) not found. Running in Pattern-Only mode.")

# --- HELPER FUNCTIONS ---
def get_outcome(n):
    try:
        val = int(float(n))
        if 0 <= val <= 4: return "SMALL"
        if 5 <= val <= 9: return "BIG"
    except: pass
    return "UNKNOWN"

# =============================================================================
# 1. MATHEMATICAL SAFETY GUARDS (THE SHIELD)
# =============================================================================

def math_trap_detector(history, window=12):
    """
    Detects 'Chopping' (Zig-Zag) markets.
    Returns: (is_trapped: bool, chop_intensity: float)
    """
    try:
        if len(history) < window: return False, 0.0
        outcomes = [get_outcome(d['actual_number']) for d in history[-window:]]
        
        # Count how many times the result flips (Big->Small or Small->Big)
        flips = sum(1 for i in range(len(outcomes)-1) if outcomes[i] != outcomes[i+1])
        chop_score = flips / (window - 1)
        
        # If > 60% of the last 12 rounds were flips, it's a trap.
        return (chop_score > 0.60), chop_score
    except: return False, 0.0

def math_streak_detector(history):
    """
    Detects strong streaks (e.g., 5 BIGs in a row).
    Returns: (streak_count: int, streak_type: str)
    """
    try:
        if not history: return 0, "NONE"
        outcomes = [get_outcome(d['actual_number']) for d in history[-15:]]
        if not outcomes: return 0, "NONE"
        
        current_type = outcomes[-1]
        count = 1
        for i in range(len(outcomes)-2, -1, -1):
            if outcomes[i] == current_type: count += 1
            else: break
        return count, current_type
    except: return 0, "NONE"

# =============================================================================
# 2. PATTERN ENGINE (THE EYES)
# =============================================================================

def engine_pattern_v3(history):
    """
    Scans for repeating sequences (e.g., B S B S -> B).
    """
    try:
        if len(history) < 60: return None
        # Convert history to string: "BBSB..."
        outcomes = "".join(["B" if get_outcome(d['actual_number']) == "BIG" else "S" for d in history])
        
        best_conf = 0.0
        best_pred = None
        
        # Look for patterns of length 4, 5, and 6
        for depth in [4, 5, 6]: 
            current_pattern = outcomes[-depth:]
            # Search entire history for this pattern
            search_space = outcomes[:-1]
            found_count = search_space.count(current_pattern)
            
            if found_count < 3: continue # Not enough data
            
            # Find what happened AFTER this pattern previously
            next_b = 0
            start_index = 0
            while True:
                idx = search_space.find(current_pattern, start_index)
                if idx == -1: break
                # Check the character immediately following the pattern
                if idx + depth < len(search_space):
                    if search_space[idx+depth] == 'B': next_b += 1
                start_index = idx + 1
            
            prob_b = next_b / found_count
            
            # Calculate deviation from 50/50
            diff = abs(prob_b - 0.5)
            
            if diff > best_conf:
                best_conf = diff
                best_pred = "BIG" if prob_b > 0.5 else "SMALL"

        # Only return if we found a significant pattern (>15% edge)
        if best_conf > 0.15:
            # Normalize confidence to 0-1 scale approx
            final_conf = 0.5 + best_conf 
            return {'pred': best_pred, 'conf': final_conf}
            
    except Exception: pass
    return None

# =============================================================================
# 3. MACHINE LEARNING ENGINE (THE BRAIN)
# =============================================================================

class SniperML:
    def __init__(self):
        self.model_xgb = None
        self.model_rf = None
        self.is_trained = False
        self.last_train_size = 0

    def train(self, history):
        """
        Trains the models ONCE. Called by fetcher at startup.
        """
        if not ML_AVAILABLE or len(history) < 100: return
        if self.is_trained and len(history) - self.last_train_size < 500: return # Don't over-train

        try:
            df = pd.DataFrame(history)
            df['val'] = df['actual_number'].astype(int)
            
            # Feature Engineering
            df['target'] = df['val'].apply(lambda x: 1 if x >= 5 else 0).shift(-1) # 1=BIG, 0=SMALL
            
            # Rolling features (Trends)
            for window in [3, 6, 12]:
                df[f'mean_{window}'] = df['val'].rolling(window).mean()
                df[f'std_{window}'] = df['val'].rolling(window).std()
            
            df = df.dropna()
            
            features = [c for c in df.columns if 'mean' in c or 'std' in c]
            X = df[features]
            y = df['target']
            
            # Train XGBoost (Fast & Accurate)
            self.model_xgb = xgb.XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.1, eval_metric='logloss')
            self.model_xgb.fit(X, y)
            
            # Train Random Forest (Robustness)
            self.model_rf = RandomForestClassifier(n_estimators=100, max_depth=5)
            self.model_rf.fit(X, y)
            
            self.is_trained = True
            self.last_train_size = len(history)
            print(f"[SNIPER ML] Training Complete. (Samples: {len(X)})")
            
        except Exception as e:
            print(f"[SNIPER ML] Training Failed: {e}")

    def predict(self, history):
        if not self.is_trained: return None
        try:
            # Prepare single row for prediction
            last_idx = len(history)
            # We need enough history to calculate the rolling windows
            subset = history[-20:] 
            df = pd.DataFrame(subset)
            df['val'] = df['actual_number'].astype(int)
            
            # Recreate features exactly as in training
            row = {}
            for window in [3, 6, 12]:
                row[f'mean_{window}'] = df['val'].rolling(window).mean().iloc[-1]
                row[f'std_{window}'] = df['val'].rolling(window).std().iloc[-1]
            
            X_pred = pd.DataFrame([row])
            
            # Get probabilities
            p_xgb = self.model_xgb.predict_proba(X_pred)[0][1] # Prob of 1 (BIG)
            p_rf = self.model_rf.predict_proba(X_pred)[0][1]
            
            avg_prob = (p_xgb + p_rf) / 2
            
            decision = "BIG" if avg_prob > 0.5 else "SMALL"
            confidence = avg_prob if decision == "BIG" else 1 - avg_prob
            
            return {'pred': decision, 'conf': confidence}
        except: return None

# Initialize Global Brain
brain = SniperML()

# =============================================================================
# 4. MAIN SNIPER LOGIC
# =============================================================================

def get_sniper_prediction(history: List[Dict]) -> Dict:
    """
    The Single Source of Truth.
    Returns: {'decision': 'BIG'/'SMALL'/'SKIP', 'reason': str}
    """
    
    # 0. TRAIN IF NEEDED (First run only usually)
    brain.train(history)
    
    # 1. SAFETY CHECKS (The Veto)
    is_chopping, chop_score = math_trap_detector(history)
    if is_chopping:
        return {'decision': 'SKIP', 'reason': f"MARKET CHOP ({chop_score:.2f})"}

    streak_len, streak_type = math_streak_detector(history)
    
    # 2. GATHER SIGNALS
    signals = []
    
    # A. ML Signal
    ml_res = brain.predict(history)
    if ml_res and ml_res['conf'] > 0.53: # Min confidence threshold
        signals.append(ml_res)
    
    # B. Pattern Signal
    pat_res = engine_pattern_v3(history)
    if pat_res:
        signals.append(pat_res)

    # 3. CONSENSUS LOGIC
    if not signals:
        return {'decision': 'SKIP', 'reason': "NO SIGNAL"}

    final_pred = None
    
    # CASE 1: ML + PATTERN Agreement (Strongest)
    if ml_res and pat_res:
        if ml_res['pred'] == pat_res['pred']:
            final_pred = ml_res['pred']
            reason = f"SNIPER LOCK (ML:{ml_res['conf']:.2f} + PAT)"
        else:
            # Conflict -> Check if one is overwhelming
            if ml_res['conf'] > 0.70: 
                final_pred = ml_res['pred']
                reason = "ML OVERRIDE"
            elif pat_res['conf'] > 0.75:
                final_pred = pat_res['pred']
                reason = "PATTERN OVERRIDE"
            else:
                return {'decision': 'SKIP', 'reason': "CONFLICT"}
    
    # CASE 2: Single Signal (Must be high confidence)
    elif ml_res:
        if ml_res['conf'] > 0.60:
            final_pred = ml_res['pred']
            reason = f"ML SOLO ({ml_res['conf']:.2f})"
        else:
            return {'decision': 'SKIP', 'reason': "WEAK ML"}
            
    elif pat_res:
        if pat_res['conf'] > 0.65:
            final_pred = pat_res['pred']
            reason = "PATTERN SOLO"
        else:
            return {'decision': 'SKIP', 'reason': "WEAK PATTERN"}

    # 4. STREAK PROTECTION
    # If we are betting AGAINST a huge streak (e.g. 5 BIGs and we bet SMALL), be careful
    if streak_len >= 5 and streak_type != final_pred:
        # Only fight a streak if we have massive confidence
        if "SNIPER LOCK" not in reason:
            return {'decision': 'SKIP', 'reason': f"RESPECT STREAK ({streak_type} {streak_len})"}

    return {'decision': final_pred, 'reason': reason}
