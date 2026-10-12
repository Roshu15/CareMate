"""SQLite persistence for CareMate. Database location can be set with CAREMATE_DB."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("CAREMATE_DB", Path(__file__).resolve().parents[1] / "caremate.db"))


@contextmanager
def connection():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_tables():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL CHECK(role IN ('caretaker','caregiver')), phone TEXT,
            language TEXT NOT NULL DEFAULT 'en', password_hash TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, date_of_birth TEXT, phone TEXT,
            notes TEXT, created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS patient_caregivers (
            patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
            caregiver_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            PRIMARY KEY(patient_id, caregiver_id)
        );
        CREATE TABLE IF NOT EXISTS caregiver_requests (
            id INTEGER PRIMARY KEY,
            patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
            caregiver_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','declined')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(patient_id,caregiver_id)
        );
        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
            filename TEXT, ocr_text TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'processed',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS medicines (
            id INTEGER PRIMARY KEY, patient_id INTEGER REFERENCES patients(id) ON DELETE CASCADE,
            prescription_id INTEGER REFERENCES prescriptions(id) ON DELETE SET NULL,
            medicine_name TEXT NOT NULL, dose TEXT NOT NULL DEFAULT '', frequency TEXT NOT NULL DEFAULT '',
            timing TEXT NOT NULL DEFAULT '', duration INTEGER NOT NULL DEFAULT 0,
            start_date TEXT NOT NULL, reminder_times TEXT NOT NULL DEFAULT '[]', rxcui TEXT,
            quantity REAL, active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS medication_logs (
            id INTEGER PRIMARY KEY, medicine_id INTEGER NOT NULL REFERENCES medicines(id) ON DELETE CASCADE,
            scheduled_date TEXT NOT NULL, scheduled_time TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('taken','missed','skipped')),
            taken_at TEXT, note TEXT, UNIQUE(medicine_id, scheduled_date, scheduled_time)
        );
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
            title TEXT NOT NULL DEFAULT 'Doctor follow-up', doctor TEXT, appointment_at TEXT NOT NULL,
            notes TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY, patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
            title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', remind_at TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'custom', completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY, patient_id INTEGER REFERENCES patients(id) ON DELETE CASCADE,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL DEFAULT 'info',
            read INTEGER NOT NULL DEFAULT 0, dedupe_key TEXT UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL, message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_logs_date ON medication_logs(scheduled_date);
        CREATE INDEX IF NOT EXISTS idx_reminders_time ON reminders(remind_at);
        """)
        # Upgrade the original prototype database without dropping user data.
        cols = {r["name"] for r in db.execute("PRAGMA table_info(medicines)")}
        for name, declaration in (("patient_id", "INTEGER REFERENCES patients(id) ON DELETE CASCADE"),
                                  ("prescription_id", "INTEGER REFERENCES prescriptions(id) ON DELETE SET NULL"),
                                  ("quantity", "REAL"), ("active", "INTEGER NOT NULL DEFAULT 1")):
            if name not in cols:
                db.execute(f"ALTER TABLE medicines ADD COLUMN {name} {declaration}")
        cols = {r["name"] for r in db.execute("PRAGMA table_info(users)")}
        if "password_hash" not in cols:
            db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        cols = {r["name"] for r in db.execute("PRAGMA table_info(notifications)")}
        if "dedupe_key" not in cols:
            db.execute("ALTER TABLE notifications ADD COLUMN dedupe_key TEXT")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_dedupe ON notifications(dedupe_key)")
        cols = {r["name"] for r in db.execute("PRAGMA table_info(medication_logs)")}
        if "medicine_id" not in cols:
            db.execute("ALTER TABLE medication_logs ADD COLUMN medicine_id INTEGER REFERENCES medicines(id) ON DELETE CASCADE")
        # Older databases predate optional dose notes; the dose API writes this field.
        if "note" not in cols:
            db.execute("ALTER TABLE medication_logs ADD COLUMN note TEXT")
        # Attach legacy dose rows to their matching medicine records, preserving history.
        if "medicine_name" in cols:
            db.execute("UPDATE medication_logs SET medicine_id=(SELECT MAX(m.id) FROM medicines m WHERE m.medicine_name=medication_logs.medicine_name) WHERE medicine_id IS NULL")
            db.execute("UPDATE medication_logs SET status=lower(status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_medicines_patient ON medicines(patient_id, active)")


def add_medicine(medicine, dose, frequency, timing, duration, start_date, reminder_times, rxcui,
                 patient_id=None, prescription_id=None, quantity=None):
    import json
    with connection() as db:
        cur = db.execute("""INSERT INTO medicines(patient_id,prescription_id,medicine_name,dose,frequency,timing,
            duration,start_date,reminder_times,rxcui,quantity) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (patient_id,prescription_id,medicine,dose,frequency,timing,duration,start_date,
             json.dumps(reminder_times),rxcui,quantity))
        return cur.lastrowid


def record_status(medicine, scheduled_date, scheduled_time, status):
    with connection() as db:
        row = db.execute("SELECT id FROM medicines WHERE medicine_name=? ORDER BY id DESC LIMIT 1", (medicine,)).fetchone()
        if not row:
            raise ValueError("Medicine not found")
        existing=db.execute("SELECT id FROM medication_logs WHERE medicine_id=? AND scheduled_date=? AND scheduled_time=? ORDER BY id DESC LIMIT 1",
                            (row["id"],scheduled_date,scheduled_time)).fetchone()
        if existing:
            db.execute("UPDATE medication_logs SET status=?,taken_at=CURRENT_TIMESTAMP WHERE id=?",(status.lower(),existing["id"]))
        else:
            db.execute("INSERT INTO medication_logs(medicine_id,scheduled_date,scheduled_time,status,taken_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)",
                       (row["id"],scheduled_date,scheduled_time,status.lower()))


create_tables()
