import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB = Path("data/signals.sqlite3")
DB.parent.mkdir(parents=True, exist_ok=True)

def init_db():
    with sqlite3.connect(DB) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT, symbol TEXT, side TEXT, entry REAL, stop REAL,
            target REAL, risk_cash REAL, status TEXT, note TEXT, order_response TEXT
        )""")

def add_signal(signal):
    with sqlite3.connect(DB) as con:
        cur = con.execute(
            "INSERT INTO signals(created_at,symbol,side,entry,stop,target,risk_cash,status,note) VALUES(?,?,?,?,?,?,?,?,?)",
            (signal["created_at"], signal["symbol"], signal["side"], signal["entry"],
             signal["stop"], signal["target"], signal["risk_cash"], "PENDING_APPROVAL", signal.get("note",""))
        )
        return cur.lastrowid

def all_signals():
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        return [dict(row) for row in con.execute("SELECT * FROM signals ORDER BY id DESC LIMIT 200")]

def get_signal(signal_id):
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        row = con.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
        return dict(row) if row else None

def update_signal(signal_id, status, note="", order_response=""):
    with sqlite3.connect(DB) as con:
        con.execute("UPDATE signals SET status=?,note=?,order_response=? WHERE id=?",
                    (status, note, order_response, signal_id))
