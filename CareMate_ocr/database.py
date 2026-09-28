import sqlite3
from datetime import datetime


def create_tables():

    connection = sqlite3.connect("caremate.db")
    cursor = connection.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS medicines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicine_name TEXT,
        dose TEXT,
        frequency TEXT,
        timing TEXT,
        duration INTEGER,
        start_date TEXT,
        reminder_times TEXT,
        rxcui TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS medication_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicine_name TEXT,
        scheduled_date TEXT,
        scheduled_time TEXT,
        status TEXT,
        taken_at TEXT
    )
    """)

    connection.commit()
    connection.close()


def add_medicine(
    medicine,
    dose,
    frequency,
    timing,
    duration,
    start_date,
    reminder_times,
    rxcui
):

    connection = sqlite3.connect("caremate.db")
    cursor = connection.cursor()

    cursor.execute("""
    INSERT INTO medicines
    (
        medicine_name,
        dose,
        frequency,
        timing,
        duration,
        start_date,
        reminder_times,
        rxcui
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        medicine,
        dose,
        frequency,
        timing,
        duration,
        start_date,
        ", ".join(reminder_times),
        rxcui
    ))

    connection.commit()
    connection.close()


def record_status(
    medicine,
    scheduled_date,
    scheduled_time,
    status
):

    connection = sqlite3.connect("caremate.db")
    cursor = connection.cursor()

    taken_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cursor.execute("""
    INSERT INTO medication_logs
    (
        medicine_name,
        scheduled_date,
        scheduled_time,
        status,
        taken_at
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        medicine,
        scheduled_date,
        scheduled_time,
        status,
        taken_at
    ))

    connection.commit()
    connection.close()


create_tables()