import sqlite3
import os
from datetime import datetime, timedelta

# RENDER CONFIGURATION
DB_PATH = '/data' if os.path.exists('/data') else '.'
DATABASE_FILE = os.path.join(DB_PATH, 'ar_lottery_history.db')

def create_connection():
    return sqlite3.connect(DATABASE_FILE)

def setup_database():
    conn = create_connection()
    cursor = conn.cursor()
    
    # 1. Results Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS results (
            issue TEXT PRIMARY KEY, 
            code INTEGER NOT NULL,
            api_timestamp REAL,
            fetch_timestamp REAL
        )
    """)

    # 2. License Keys Table (Updated with max_devices)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS access_keys (
            key_code TEXT PRIMARY KEY,
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            expires_at TIMESTAMP,
            max_devices INTEGER DEFAULT 1
        )
    """)

    # 3. Active Sessions Table (NEW: Tracks currently logged in users)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_sessions (
            session_id TEXT PRIMARY KEY,
            key_code TEXT,
            last_seen TIMESTAMP
        )
    """)
    
    # --- AUTO-MIGRATION: Fix old databases ---
    try:
        cursor.execute("SELECT max_devices FROM access_keys LIMIT 1")
    except sqlite3.OperationalError:
        print("Upgrading Database: Adding max_devices column...")
        cursor.execute("ALTER TABLE access_keys ADD COLUMN max_devices INTEGER DEFAULT 1")
        conn.commit()

    conn.commit()
    conn.close()

# --- HELPER: CLEANUP OLD SESSIONS ---
def cleanup_inactive_sessions():
    """Removes sessions that haven't pinged in 60 seconds."""
    conn = create_connection()
    # Delete sessions older than 1 minute
    cutoff = datetime.now() - timedelta(seconds=60)
    conn.execute("DELETE FROM active_sessions WHERE last_seen < ?", (cutoff,))
    conn.commit()
    conn.close()

async def save_result_to_database(data_to_save):
    # (Same as before - no changes needed here)
    conn = create_connection()
    cursor = conn.cursor()
    new_records = False
    try:
        batch = []
        for record in data_to_save:
            batch.append((str(record['issue']), int(record['code']), record.get('api_timestamp'), record.get('fetch_timestamp')))
        cursor.executemany("INSERT OR IGNORE INTO results (issue, code, api_timestamp, fetch_timestamp) VALUES (?, ?, ?, ?)", batch)
        if cursor.rowcount > 0: new_records = True
        conn.commit()
    except: pass
    finally: conn.close()
    return new_records

def ensure_setup():
    setup_database()
