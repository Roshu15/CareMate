import os
import sqlite3
import time
import threading
from datetime import datetime


DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "caremate.db"
)


GRACE_PERIOD = 1  # minutes


def get_medicines():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute("""
    SELECT
        medicine_name,
        dose,
        reminder_times,
        start_date,
        duration
    FROM medicines
    """)

    medicines = cursor.fetchall()
    connection.close()

    return medicines


def record_status(
    medicine,
    scheduled_date,
    scheduled_time,
    status
):
    connection = sqlite3.connect("caremate.db")
    cursor = connection.cursor()

    taken_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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


def handle_reminder(
    name,
    dose,
    scheduled_date,
    scheduled_time
):

    print("\n🔔 MEDICINE REMINDER")
    print("Medicine:", name)
    print("Dose:", dose)
    print("Scheduled time:", scheduled_time)

    print("\n1. Taken")
    print("2. Missed")

    # Wait for user response in a separate thread
    def get_response():

        choice = input("Enter your choice: ")

        if choice == "1":
            record_status(
                name,
                scheduled_date,
                scheduled_time,
                "Taken"
            )
            print("✅ Status saved: Taken")

        elif choice == "2":
            record_status(
                name,
                scheduled_date,
                scheduled_time,
                "Missed"
            )
            print("❌ Status saved: Missed")

    thread = threading.Thread(
        target=get_response,
        daemon=True
    )

    thread.start()

    # Wait for grace period
    time.sleep(GRACE_PERIOD * 60)

    # Check whether response was given
    if thread.is_alive():

        record_status(
            name,
            scheduled_date,
            scheduled_time,
            "Missed"
        )

        print("\n⏰ Missed dose detected")
        print("Medicine:", name)
        print("Scheduled date:", scheduled_date)
        print("Scheduled time:", scheduled_time)
        print("Status: Missed")


reminders_triggered = set()


while True:

    now = datetime.now()
    today = now.date()

    medicines = get_medicines()

    for medicine in medicines:

        name = medicine[0]
        dose = medicine[1]
        reminder_times = medicine[2].split(", ")

        start_date = datetime.strptime(
            medicine[3],
            "%Y-%m-%d"
        ).date()

        duration = medicine[4]

        end_date = start_date.fromordinal(
            start_date.toordinal() + duration - 1
        )

        if not (start_date <= today <= end_date):
            continue

        for reminder_time in reminder_times:

            reminder_datetime = datetime.strptime(
                f"{today} {reminder_time}",
                "%Y-%m-%d %I:%M %p"
            )

            reminder_key = (
                str(today),
                name,
                reminder_time
            )

            if (
                now >= reminder_datetime
                and now < reminder_datetime.fromtimestamp(
                    reminder_datetime.timestamp() + 60
                )
                and reminder_key not in reminders_triggered
            ):

                reminders_triggered.add(reminder_key)

                threading.Thread(
                    target=handle_reminder,
                    args=(
                        name,
                        dose,
                        str(today),
                        reminder_time
                    ),
                    daemon=True
                ).start()

    time.sleep(60)