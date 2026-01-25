# ==============================================================================
# MODULE: PREDICTION_ENGINE.PY (V2026.42 - TITAN NEURAL EMULATOR)
# ==============================================================================
import math
import statistics
import asyncio
import aiohttp
import json
import warnings
import time
import random
from collections import defaultdict, deque
from typing import Dict, List, Optional, Any

warnings.filterwarnings("ignore")

# --- ML IMPORTS ---
try:
    import pandas as pd
    import numpy as np
    from sklearn.neural_network import MLPClassifier
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
except ImportError:
    pd = None
    print("[WARN] Pandas/Sklearn not found. ML features disabled.")

# --- XGBOOST IMPORT ---
try:
    import xgboost as xgb
    XGB_AVAILABLE = True
except ImportError:
    XGB_AVAILABLE = False
    print("[WARN] XGBoost not found. XGB engine disabled.")

# --- CONFIG ---
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"

# --- HELPER FUNCTIONS ---
def safe_float(value):
    try: return float(value)
    except: return 4.5

def get_outcome_from_number(n):
    val = int(safe_float(n))
    if 0 <= val <= 4: return "SMALL"
    if 5 <= val <= 9: return "BIG"
    return "Unknown"

def get_outcome(n):
    return get_outcome_from_number(n)

# =============================================================================
# 1. MATH CORE LOGIC
# =============================================================================

def math_trap_detector(history, window=12):
    try:
        if len(history) < window: return False, 0.0
        outcomes = [get_outcome(d['actual_number']) for d in history[-window:]]
        flips = sum(1 for i in range(len(outcomes)-1) if outcomes[i] != outcomes[i+1])
        trap_score = flips / (window - 1)
        return (trap_score > 0.65), trap_score
    except: return False, 0.0

def math_streak_finder(history):
    try:
        if not history: return 0
        outcomes = [get_outcome(d['actual_number']) for d in history[-20:]]
        if not outcomes: return 0
        current = outcomes[-1]
        cnt = 1
        for i in range(len(outcomes)-2, -1, -1):
            if outcomes[i] == current: cnt += 1
            else: break
        return cnt if current == "BIG" else -cnt
    except: return 0

def math_volatility(history, window=20):
    try:
        if len(history) < window: return 0.0
        nums = [1 if get_outcome(d['actual_number']) == "BIG" else 0 for d in history[-window:]]
        return statistics.pstdev(nums)
    except: return 0.0

# =============================================================================
# 2. STANDARD ENGINES
# =============================================================================

def engine_quantum_adaptive(history):
    try:
        nums = [safe_float(d['actual_number']) for d in history[-30:]]
        if len(nums) < 20: return None
        mean = statistics.mean(nums)
        std = statistics.stdev(nums) if len(nums) > 1 else 0
        if std == 0: return None
        z = (nums[-1] - mean) / std
        strength = min(abs(z) / 2.2, 1.0)
        if z > 1.1: return {'pred': "SMALL", 'conf': strength, 'name': 'QUANTUM'}
        if z < -1.1: return {'pred': "BIG", 'conf': strength, 'name': 'QUANTUM'}
    except: pass
    return None

def engine_deep_pattern_v3(history):
    try:
        if len(history) < 60: return None
        outcomes = "".join(["B" if get_outcome(d['actual_number']) == "BIG" else "S" for d in history])
        best_conf = 0; best_pred = None
        for depth in range(6, 3, -1): 
            pat = outcomes[-depth:]
            search = outcomes[:-1]
            cnt = search.count(pat)
            if cnt < 3: continue
            next_b = 0; start = 0
            while True:
                idx = search.find(pat, start)
                if idx == -1: break
                if idx + depth < len(search):
                    if search[idx+depth] == 'B': next_b += 1
                start = idx + 1
            prob_b = next_b / cnt
            diff = abs(prob_b - 0.5) * 2 
            if diff > best_conf and diff > 0.14: 
                best_conf = diff
                best_pred = "BIG" if prob_b > 0.5 else "SMALL"
        if best_conf > 0:
            return {'pred': best_pred, 'conf': best_conf, 'name': 'PATTERN'}
    except: pass
    return None

def engine_markov_matrix(history):
    try:
        if len(history) < 50: return None
        outcomes = [get_outcome(d['actual_number']) for d in history]
        last_2 = tuple(outcomes[-2:])
        transitions = defaultdict(int)
        for i in range(len(outcomes) - 2):
            curr = tuple(outcomes[i:i+2])
            nxt = outcomes[i+2]
            if curr == last_2:
                transitions[nxt] += 1
        total = transitions["BIG"] + transitions["SMALL"]
        if total < 5: return None
        p_big = transitions["BIG"] / total
        if p_big > 0.54: return {'pred': "BIG", 'conf': p_big, 'name': 'MARKOV'}
        if p_big < 0.46: return {'pred': "SMALL", 'conf': 1-p_big, 'name': 'MARKOV'}
    except: pass
    return None

# =============================================================================
# 3. PERFORMANCE TRACKER (DYNAMIC WEIGHTING)
# =============================================================================

class EnginePerformanceTracker:
    def __init__(self):
        # Stores history of votes: {'ML': ['WIN', 'LOSS', 'WIN'], ...}
        self.history = defaultdict(lambda: deque(maxlen=10)) 
        self.base_weights = {
            'ML': 1.5, 'XGB': 1.5, 'OLLAMA': 1.5, 
            'PATTERN': 1.0, 'QUANTUM': 1.0, 'MARKOV': 1.0
        }

    def update_performance(self, last_votes, actual_outcome):
        """Called after we know the real result to grade the engines."""
        if not last_votes or not actual_outcome: return
        for engine, prediction in last_votes.items():
            if prediction == actual_outcome:
                self.history[engine].append(1) # Win
            else:
                self.history[engine].append(0) # Loss

    def get_dynamic_weight(self, engine_name):
        """Calculates weight based on recent accuracy."""
        base = self.base_weights.get(engine_name, 1.0)
        stats = self.history.get(engine_name, [])
        
        if not stats: return base # No history, use default
        
        # Calculate recent win rate (last 10 rounds)
        win_rate = sum(stats) / len(stats)
        
        # LOGIC: 
        # If Win Rate > 70%, Boost Weight by 1.5x
        # If Win Rate < 30%, Slash Weight by 0.5x
        if win_rate >= 0.7: return base * 1.5
        if win_rate <= 0.3: return base * 0.5
        return base

# Initialize global tracker
performance_tracker = EnginePerformanceTracker()

# =============================================================================
# 4. DEEP BRAIN (NOW WITH NEURAL EMULATOR)
# =============================================================================

class TitanDeepBrain:
    def __init__(self):
        self.scaler = StandardScaler() if pd else None
        self.models_ready = False
        self.m1 = None; self.m2 = None; self.m3 = None 
        self.last_train_round = 0
        self.perspectives = ["Analyze sequence.", "Analyze volatility.", "Intuition."]

    def train_ensemble(self, history, current_round_id):
        # Retrain every 15 rounds
        if self.models_ready and (current_round_id - self.last_train_round < 15): return
        
        # [STRATEGY UPDATE] Use last 300 rounds only (Keeps logic fresh)
        training_subset = history[-300:] if len(history) > 300 else history
        
        if not pd or len(training_subset) < 60: return
        try:
            df = pd.DataFrame(training_subset)
            df['num'] = df['actual_number'].astype(int)
            df['label'] = df['num'].apply(lambda x: 1 if x >= 5 else 0)
            
            # Use Rolling(6) for 300 rounds (better responsiveness than 8)
            df['rmean'] = df['num'].rolling(6).mean()
            df['std'] = df['num'].rolling(6).std()
            
            df = df.fillna(0)
            df['target'] = df['label'].shift(-1)
            train_df = df.dropna()
            
            X = train_df[['rmean', 'std', 'num']]
            y = train_df['target']
            X_s = self.scaler.fit_transform(X)

            self.m1 = MLPClassifier(hidden_layer_sizes=(50,), max_iter=300).fit(X_s, y)
            self.m2 = RandomForestClassifier(n_estimators=50, max_depth=6).fit(X, y)
            if XGB_AVAILABLE:
                self.m3 = xgb.XGBClassifier(n_estimators=50, max_depth=5, eval_metric='logloss').fit(X, y)
            self.models_ready = True
            self.last_train_round = current_round_id
        except: pass

    def _mimic_intuition(self, history):
        """
        FALLBACK: Simulates AI thinking using statistical heuristics.
        Called when Ollama is offline to ensure 'Titan Consensus' still works.
        """
        try:
            if len(history) < 20: return None, 0.0
            
            # 1. Volatility Check (Chaos Theory)
            val_nums = [int(safe_float(d['actual_number'])) for d in history[-12:]]
            std_dev = statistics.stdev(val_nums) if len(val_nums) > 1 else 0
            
            # 2. Pattern Momentum (Trend Logic)
            last_6 = [get_outcome(d['actual_number']) for d in history[-6:]]
            b_count = last_6.count("BIG")
            
            # MIMIC LOGIC:
            vote = None
            if std_dev > 2.8: 
                # High Chaos -> Reversal Probability High
                if last_6[-1] == "BIG": vote = "SMALL"
                else: vote = "BIG"
            elif std_dev < 1.5: 
                # Low Chaos -> Trend Follow Probability High
                if b_count > 3: vote = "BIG"
                else: vote = "SMALL"
            else:
                # Balanced -> Use Pattern Balance
                if b_count > 3: vote = "SMALL" # Revert to mean
                else: vote = "BIG"

            return vote, 0.70 # Synthetic confidence
        except:
            return None, 0.0

    async def forced_contemplation_loop(self, history, time_budget):
        start_time = time.time()
        votes = []
        nums = [d['actual_number'] for d in history[-20:]]
        
        # 1. TRY REAL OLLAMA
        ollama_alive = False
        try:
            # Quick check if port is open/responding before loop
            async with aiohttp.ClientSession() as s:
                async with s.get("http://localhost:11434/", timeout=1) as r:
                    if r.status == 200: ollama_alive = True
        except: 
            ollama_alive = False

        if ollama_alive:
            for task in self.perspectives:
                if time.time() > start_time + (time_budget - 2): break
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.post(OLLAMA_URL, json={"model":OLLAMA_MODEL, "prompt":f"Data:{nums} Task:{task} JSON:{{'prediction':'BIG'/'SMALL'}}", "stream":False, "format":"json"}, timeout=8) as r:
                            if r.status==200:
                                js = await r.json()
                                pred = json.loads(js['response']).get('prediction')
                                if pred: votes.append(pred.upper())
                except: pass
        
        # 2. FALLBACK: USE MIMIC IF OLLAMA FAILED
        if not votes:
            # print("   [INFO] Ollama silent. Engaging Neural Emulator.") # Optional Log
            mimic_vote, mimic_conf = self._mimic_intuition(history)
            if mimic_vote: 
                return mimic_vote, mimic_conf
            return None, 0.0

        big = votes.count("BIG"); small = votes.count("SMALL")
        if big > small: return "BIG", big/(big+small)
        elif small > big: return "SMALL", small/(big+small)
        return None, 0.0

brain = TitanDeepBrain()

# =============================================================================
# 5. MAIN CONTROLLER (TITAN V2026.42 - EMULATOR INTEGRATED)
# =============================================================================

async def ultraAIPredict(history: List[Dict], current_bankroll: float, last_win_status="WIN", current_momentum=0.0, ghost_wins_streak=0, ghost_loss_streak=0, time_budget: int = 30) -> Dict:
    
    # 0. UPDATE PERFORMANCE TRACKER (Done via report_outcome_to_tracker)
    
    try:
        last_num = int(history[-1]['actual_number'])
    except:
        return {'finalDecision': "SKIP", 'confidence': 0, 'level': "ERR", 'reason': "Bad Data", 'raw_votes': {}}

    is_trap_number = (last_num == 0 or last_num == 5)
    is_chopping, chop_score = math_trap_detector(history)
    streak_val = math_streak_finder(history)
    streak_len = abs(streak_val)
    vol_score = math_volatility(history)

    # --- B. BACKGROUND TRAINING ---
    await asyncio.to_thread(brain.train_ensemble, history, int(history[-1]['issue']))

    # --- C. OLLAMA (OR EMULATOR) ---
    ollama_pred = None; ollama_conf = 0.0
    try: ollama_pred, ollama_conf = await brain.forced_contemplation_loop(history, time_budget)
    except: pass

    # --- D. GATHER SIGNALS ---
    raw_signals = {}
    
    if brain.models_ready and pd and brain.m3:
        try:
            df = pd.DataFrame(history); df['num'] = df['actual_number'].astype(int)
            df['rmean'] = df['num'].rolling(6).mean(); df['std'] = df['num'].rolling(6).std()
            df = df.fillna(0); last = df.iloc[[-1]][['rmean', 'std', 'num']]
            p3 = brain.m3.predict_proba(last)[0][1]
            if p3 > 0.51: raw_signals['XGB'] = {'pred': "BIG", 'conf': p3} 
            elif p3 < 0.49: raw_signals['XGB'] = {'pred': "SMALL", 'conf': 1-p3}
        except: pass

    if brain.models_ready and pd:
         try:
            df = pd.DataFrame(history); df['num'] = df['actual_number'].astype(int)
            df['rmean'] = df['num'].rolling(6).mean(); df['std'] = df['num'].rolling(6).std()
            df = df.fillna(0); last = df.iloc[[-1]][['rmean', 'std', 'num']]
            p1 = brain.m1.predict_proba(brain.scaler.transform(last))[0][1]
            p2 = brain.m2.predict_proba(last)[0][1]
            ml_prob = (p1 + p2) / 2
            if ml_prob > 0.51: raw_signals['ML'] = {'pred': "BIG", 'conf': ml_prob} 
            elif ml_prob < 0.49: raw_signals['ML'] = {'pred': "SMALL", 'conf': 1-ml_prob}
         except: pass

    if ollama_pred: raw_signals['OLLAMA'] = {'pred': ollama_pred, 'conf': ollama_conf}
    if (e := engine_deep_pattern_v3(history)): raw_signals['PATTERN'] = e
    if (e := engine_quantum_adaptive(history)): raw_signals['QUANTUM'] = e
    if (e := engine_markov_matrix(history)): raw_signals['MARKOV'] = e

    # --- E. DYNAMIC SCORING (THE UPGRADE) ---
    big_points = 0.0
    small_points = 0.0
    vote_display = {}

    for name, sig in raw_signals.items():
        # GET DYNAMIC WEIGHT
        points = performance_tracker.get_dynamic_weight(name)
        vote_display[name] = f"{sig['pred']} (w={points:.1f})"
        
        if sig['pred'] == "BIG": big_points += points
        else: small_points += points
    
    # --- [CONFLICT VETO] ---
    # If XGB and Pattern disagree, force SKIP
    xgb_sig = raw_signals.get('XGB', {}).get('pred')
    pat_sig = raw_signals.get('PATTERN', {}).get('pred')
    if xgb_sig and pat_sig and xgb_sig != pat_sig:
        # Check if both are relatively confident
        if raw_signals['XGB']['conf'] > 0.6 and raw_signals['PATTERN']['conf'] > 0.15:
            return {'finalDecision': "SKIP", 'confidence': 0, 'level': "SKIP", 'reason': "Conflict Veto", 'raw_votes': vote_display}
    # ---------------------------

    if big_points > small_points:
        final_decision = "BIG"
        raw_score = big_points - small_points
    else:
        final_decision = "SMALL"
        raw_score = small_points - big_points

    # --- F. SMART ADJUSTMENTS ---
    net_score = raw_score
    if is_chopping: net_score -= 1.5; vote_display['CHOP'] = "-1.5"
    if streak_len >= 3:
        streak_pred = "BIG" if streak_val > 0 else "SMALL"
        if streak_pred == final_decision: net_score += 0.5; vote_display['TREND'] = "+0.5"
        else: net_score -= 0.5; vote_display['TREND'] = "FIGHTING"
    if is_trap_number: net_score -= 0.8
    if current_momentum != 0: net_score += current_momentum
    if ghost_wins_streak >= 2: net_score += 0.5
    
    # --- G. DECISION LOGIC (TITAN CONSENSUS & OVERRIDE) ---
    REAL_THRESHOLD = 1.25; GHOST_THRESHOLD = 0.5; RECOVERY_THRESHOLD = 2.0
    if last_win_status == "LOSS": REAL_THRESHOLD = RECOVERY_THRESHOLD; vote_display['MODE'] = "RECOVERY"
    
    is_volatile = vol_score > 0.48
    hot_hand_unlock = (ghost_wins_streak >= 2)
    reversal_unlock = (ghost_loss_streak >= 2 and net_score >= 4.5)
    
    # [FIX] Do we have Consensus? (OLLAMA now backed by Emulator)
    ml_vote = raw_signals.get('ML', {}).get('pred')
    ollama_vote = raw_signals.get('OLLAMA', {}).get('pred')
    pat_vote = raw_signals.get('PATTERN', {}).get('pred')

    titan_consensus = False
    
    # Priority 1: AI Sync (Works with Real Ollama OR Emulator)
    if ml_vote and ollama_vote and ml_vote == ollama_vote:
        titan_consensus = True
    # Priority 2: Fallback Sync (ML + PATTERN) if even Emulator is unsure
    elif ml_vote and pat_vote and ml_vote == pat_vote:
        titan_consensus = True 

    if titan_consensus and ml_vote == final_decision:
        net_score += 1.0 # Bonus for AI agreement
        vote_display['AI_SYNC'] = "+1.0"

    # Override: If score is massive (>= 5.0), we force TITAN logic
    titan_override = (net_score >= 5.0)
    
    can_bypass_volatility = hot_hand_unlock or reversal_unlock or titan_override

    if is_volatile and not can_bypass_volatility:
        level = "GHOST_SIM"; vote_display['MODE'] = "VOLATILITY_LOCKED"
    elif net_score >= REAL_THRESHOLD:
        level = "L1_SCOUT"
        if net_score >= 3.0: level = "L2_LEADER"
        
        # [TITAN LOGIC]
        if net_score >= 4.2:
            if titan_consensus or titan_override:
                level = "L3_TITAN"
            else:
                level = "L2_LEADER"
                vote_display['TITAN_DENIED'] = "NO_SYNC"
                
    elif net_score >= GHOST_THRESHOLD and not is_trap_number and not is_chopping:
        level = "GHOST_SIM"
    else:
        level = "SKIP"; final_decision = "SKIP"

    return {
        'finalDecision': final_decision,
        'confidence': net_score,
        'level': level,
        'reason': f"Score: {net_score:.1f}",
        'raw_votes': vote_display
    }

# Helper to allow fetcher to update tracker
def report_outcome_to_tracker(raw_votes, actual_outcome):
    # raw_votes format: {'XGB': 'BIG (w=1.5)', ...}
    parsed_votes = {}
    for k, v in raw_votes.items():
        if "BIG" in v: parsed_votes[k] = "BIG"
        elif "SMALL" in v: parsed_votes[k] = "SMALL"
    performance_tracker.update_performance(parsed_votes, actual_outcome)
