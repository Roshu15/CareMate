import sqlite3

import os
import sqlite3

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "caremate.db"
)

connection = sqlite3.connect(DB_PATH)
cursor = connection.cursor()

cursor.execute("""
UPDATE medicines
SET reminder_times = ?
WHERE medicine_name = ?
""", ("07:41 PM", "Paracetamol"))

connection.commit()
connection.close()

print("Reminder time updated successfully.")