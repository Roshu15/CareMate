import sqlite3


def get_adherence():

    connection = sqlite3.connect("caremate.db")
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        medicine_name,
        COUNT(*) AS total,
        SUM(CASE WHEN status = 'Taken' THEN 1 ELSE 0 END) AS taken,
        SUM(CASE WHEN status = 'Missed' THEN 1 ELSE 0 END) AS missed
    FROM medication_logs
    GROUP BY medicine_name
    """)

    results = cursor.fetchall()

    connection.close()

    print("\n========== ADHERENCE REPORT ==========\n")

    for medicine in results:

        name = medicine[0]
        total = medicine[1]
        taken = medicine[2]
        missed = medicine[3]

        adherence = (taken / total) * 100 if total > 0 else 0

        print("Medicine:", name)
        print("Total doses:", total)
        print("Taken:", taken)
        print("Missed:", missed)
        print("Adherence:", round(adherence, 2), "%")
        print("----------------------------------------")


if __name__ == "__main__":
    get_adherence()