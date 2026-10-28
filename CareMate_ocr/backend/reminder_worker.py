"""Durable in-app reminder poller. Notifications are stored for clients to fetch."""
import asyncio
import json
import logging
import os
from datetime import date, datetime, timedelta

from . import database as store

log = logging.getLogger("caremate.reminders")
POLL_SECONDS = max(10, int(os.getenv("CAREMATE_REMINDER_POLL_SECONDS", "20")))
DOSE_GRACE_MINUTES = max(1, int(os.getenv("CAREMATE_DOSE_GRACE_MINUTES", "30")))


def _recipients(db, patient_id):
    rows = db.execute("SELECT created_by AS id FROM patients WHERE id=? AND created_by IS NOT NULL UNION SELECT caregiver_id AS id FROM patient_caregivers WHERE patient_id=?",
                      (patient_id, patient_id)).fetchall()
    return [row["id"] for row in rows]


def _notify(db, patient_id, dedupe_key, title, body, kind):
    recipients = _recipients(db, patient_id)
    if not recipients:
        recipients = [None]
    for user_id in recipients:
        key = f"{dedupe_key}:u{user_id if user_id is not None else 'all'}"
        db.execute("INSERT OR IGNORE INTO notifications(patient_id,user_id,title,body,kind,dedupe_key) VALUES(?,?,?,?,?,?)",
                   (patient_id,user_id,title,body,kind,key))


def _times(raw):
    try:
        values=json.loads(raw or "[]")
        if not isinstance(values,list): values=[]
    except (ValueError,TypeError):
        values=[value.strip() for value in (raw or "").split(",") if value.strip()]
    result=[]
    for value in values:
        try: result.append(datetime.strptime(value,"%I:%M %p").strftime("%H:%M"))
        except (ValueError,TypeError): result.append(value)
    return result


def process_due_items(now=None):
    """Process all due events; unique notification keys make repeated polling safe."""
    now = now or datetime.now().astimezone()
    today = now.date()
    with store.connection() as db:
        medicines = db.execute("SELECT m.*,p.name AS patient_name FROM medicines m JOIN patients p ON p.id=m.patient_id WHERE m.active=1 AND m.patient_id IS NOT NULL").fetchall()
        for med in medicines:
            try:
                start = date.fromisoformat(med["start_date"])
                times = _times(med["reminder_times"])
            except (ValueError, TypeError):
                continue
            if today < start or (med["duration"] and today >= start + timedelta(days=med["duration"])):
                continue
            first_day=max(start,today-timedelta(days=7))
            active_end=start+timedelta(days=med["duration"]-1) if med["duration"] else today
            last_day=min(today,active_end)
            schedule_day=first_day
            while schedule_day<=last_day:
                for time_text in times:
                    try:
                        scheduled = datetime.combine(schedule_day, datetime.strptime(time_text, "%H:%M").time()).astimezone()
                    except (ValueError, TypeError):
                        continue
                    if now < scheduled:
                        continue
                    scheduled_date=schedule_day.isoformat()
                    dose_key = f"dose:{med['id']}:{scheduled_date}:{time_text}"
                    log_row = db.execute("SELECT status FROM medication_logs WHERE medicine_id=? AND scheduled_date=? AND scheduled_time=?",
                                         (med["id"],scheduled_date,time_text)).fetchone()
                    if log_row:
                        continue
                    elapsed = now - scheduled
                    if elapsed >= timedelta(minutes=DOSE_GRACE_MINUTES):
                        db.execute("INSERT OR IGNORE INTO medication_logs(medicine_id,scheduled_date,scheduled_time,status) VALUES(?,?,?,'missed')",
                                   (med["id"],scheduled_date,time_text))
                        _notify(db,med["patient_id"],dose_key+":missed",f"Missed medicine dose for {med['patient_name']}",
                                f"{med['patient_name']} missed {med['medicine_name']} ({med['dose']}) at {time_text} on {scheduled_date}.","missed_dose")
                    else:
                        _notify(db,med["patient_id"],dose_key,"Medicine reminder",
                                f"Time for {med['medicine_name']} ({med['dose']}) at {time_text}. Please confirm whether it was taken.","medicine")
                schedule_day+=timedelta(days=1)

            # Refill estimate uses the entered quantity and scheduled doses/day.
            if med["quantity"] is not None:
                elapsed_days = max(0, (today - start).days)
                per_day = len(times)
                estimated_left = med["quantity"] - elapsed_days * per_day
                if per_day and 0 <= estimated_left <= per_day * 3:
                    _notify(db,med["patient_id"],f"refill:{med['id']}:qty:{med['quantity']}","Medicine refill soon",
                            f"Estimated supply of {med['medicine_name']} is about {max(0,estimated_left):g} doses. Contact the prescriber or pharmacy to arrange a refill.","refill")
            elif med["duration"]:
                days_left = med["duration"] - max(0,(today-start).days)
                if 0 < days_left <= 3:
                    _notify(db,med["patient_id"],f"refill:{med['id']}:duration:{med['duration']}","Medicine course ending soon",
                            f"{med['medicine_name']} is scheduled to end in {days_left} day(s). Follow the prescription and ask the prescriber about any continuation.","refill")

        custom = db.execute("SELECT * FROM reminders WHERE completed=0 AND remind_at<=?",(now.isoformat(timespec="seconds"),)).fetchall()
        for reminder in custom:
            _notify(db,reminder["patient_id"],f"reminder:{reminder['id']}",reminder["title"],reminder["body"],reminder["kind"])
            db.execute("UPDATE reminders SET completed=1 WHERE id=?",(reminder["id"],))

        appointments = db.execute("SELECT * FROM appointments WHERE appointment_at>? AND appointment_at<=?",
            (now.isoformat(timespec="seconds"),(now+timedelta(hours=25)).isoformat(timespec="seconds"))).fetchall()
        for appointment in appointments:
            _notify(db,appointment["patient_id"],f"appointment:{appointment['id']}","Doctor follow-up tomorrow",
                    f"{appointment['title']} is scheduled for {appointment['appointment_at']}.","appointment")


async def run_reminder_worker():
    log.info("CareMate in-app reminder worker started; polling every %s seconds",POLL_SECONDS)
    while True:
        try:
            await asyncio.to_thread(process_due_items)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Reminder processing failed; will retry on next poll")
        await asyncio.sleep(POLL_SECONDS)
