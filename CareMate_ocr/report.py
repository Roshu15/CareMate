import sqlite3

connection = sqlite3.connect("caremate.db")
cursor = connection.cursor()

# Get medication status
cursor.execute("""
SELECT medicine_name,
       SUM(CASE WHEN status = 'Taken' THEN 1 ELSE 0 END),
       SUM(CASE WHEN status = 'Missed' THEN 1 ELSE 0 END)
FROM medication_logs
GROUP BY medicine_name
""")

results = cursor.fetchall()

print("\n========== CAREMATE ADHERENCE REPORT ==========\n")

total_taken = 0
total_missed = 0

for medicine in results:
    name = medicine[0]
    taken = medicine[1]
    missed = medicine[2]

    total_taken += taken
    total_missed += missed

    total = taken + missed
    adherence = (taken / total) * 100 if total > 0 else 0

    print("Medicine:", name)
    print("Taken:", taken)
    print("Missed:", missed)
    print("Adherence:", round(adherence, 2), "%")
    print("--------------------------------------------")

# Overall adherence
total_doses = total_taken + total_missed

if total_doses > 0:
    overall_adherence = (total_taken / total_doses) * 100
else:
    overall_adherence = 0

print("\n========== OVERALL ==========")
print("Total Taken:", total_taken)
print("Total Missed:", total_missed)
print("Overall Adherence:", round(overall_adherence, 2), "%")

connection.close()