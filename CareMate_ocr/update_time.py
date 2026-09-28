import sqlite3

connection = sqlite3.connect("caremate.db")
cursor = connection.cursor()

cursor.execute("""
UPDATE medicines
SET reminder_times = ?
WHERE medicine_name = ?
""", ("04:29 PM", "Paracetamol"))

connection.commit()
connection.close()

print("Reminder time updated successfully.")