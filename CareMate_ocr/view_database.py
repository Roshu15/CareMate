import sqlite3

connection = sqlite3.connect("caremate.db")
cursor = connection.cursor()

cursor.execute("""
SELECT
    medicine_name,
    dose,
    frequency,
    timing,
    duration,
    reminder_times,
    rxcui
FROM medicines
""")

medicines = cursor.fetchall()

print("\n========== STORED MEDICINES ==========\n")

for medicine in medicines:
    print("Medicine:", medicine[0])
    print("Dose:", medicine[1])
    print("Frequency:", medicine[2])
    print("Timing:", medicine[3])
    print("Duration:", medicine[4], "days")
    print("Reminder Times:", medicine[5])
    print("RxCUI:", medicine[6])
    print("----------------------------------------")

connection.close()