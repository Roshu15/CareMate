# CareMate backend

FastAPI service for CareMate. SQLite data is stored in `caremate.db` beside this folder unless `CAREMATE_DB` points to a different file. On startup, the backend upgrades the original prototype schema without dropping its medicine and dose history.

See [CAREMATE_PROJECT_GUIDE.md](CAREMATE_PROJECT_GUIDE.md) for the project architecture, technology stack, source-file explanations, database, API reference, setup, and current limitations.

## Project layout

- `backend/` contains the FastAPI application and backend modules.
- `frontend/` contains the static HTML, CSS, and JavaScript application.
- `scripts/legacy/` contains standalone scripts retained from earlier project stages; the web application does not depend on most of them.
- `app.py` at the project root is a small launcher kept for compatibility with the command below.
- `caremate.db` stays in the project root so existing user data remains in place.

## Start locally

```powershell
cd CareMate_ocr
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:OCR_SPACE_API_KEY = "your-ocr.space-api-key"
uvicorn app:app --reload
```

The CareMate web app is served at `http://127.0.0.1:8000/`, API docs are at `/docs`, and `/health` is the health check. Serving the interface and API together avoids separate frontend setup. Set `CAREMATE_CORS_ORIGINS` only if you later host the frontend separately. The API starts its in-app reminder worker automatically. Poll interval defaults to 20 seconds (`CAREMATE_REMINDER_POLL_SECONDS`); dose confirmation grace period defaults to 30 minutes (`CAREMATE_DOSE_GRACE_MINUTES`).

## Authentication

Register or log in first:

```http
POST /api/auth/register
Content-Type: application/json
```

```json
{"name":"Alex","email":"alex@example.com","role":"caretaker","password":"at-least-10-characters","language":"en"}
```

Both registration and login return `access_token`. A Caretaker account represents the patient and receives a patient profile automatically. Send the token on protected requests as `Authorization: Bearer <access_token>`. Sessions expire after 14 days and can be revoked with `/api/auth/logout`. `/api/auth/me` returns the current user; `/api/auth/change-password` changes the password and revokes existing sessions. Supported language codes are returned by `GET /api/languages`. Patients are visible to their caretaker and linked caregivers only.

## API overview

- Patients: `GET /api/patients`, `GET/PATCH /api/patients/{id}`. Caregivers request access with `POST /api/caregiver-requests` using the patient's caretaker email; the patient approves or declines with `PATCH /api/caregiver-requests/{id}`. See requests with `GET /api/caregiver-requests`.
- Prescriptions: `POST /api/patients/{id}/prescriptions/ocr` (multipart field `image`; JPEG/PNG/WEBP/TIFF, max 10 MB), `GET /api/patients/{id}/prescriptions`, `GET /api/prescriptions/{id}`.
- Medicines: `POST/GET /api/patients/{id}/medicines`, `PATCH/DELETE /api/medicines/{id}`. Reminder times use 24-hour `HH:MM`.
- Schedule and adherence: `GET /api/patients/{id}/schedule?on=YYYY-MM-DD`, `POST /api/medicines/{id}/doses`, `GET /api/patients/{id}/doses`, `GET /api/patients/{id}/reports/adherence`.
- Follow-ups and custom reminders: `POST/GET /api/patients/{id}/appointments`, `PATCH/DELETE /api/appointments/{id}`, `POST/GET /api/patients/{id}/reminders`, `PATCH/DELETE /api/reminders/{id}`.
- Notifications and support: `GET /api/notifications`, `PATCH /api/notifications/{id}/read`, `POST /api/contact`, `POST /api/chat`, `GET /api/rxnorm?name=...`.

## Medication plan example

```json
{
  "medicine_name": "Example medicine",
  "dose": "500 mg",
  "frequency": "1-0-1",
  "timing": "after food",
  "duration": 5,
  "start_date": "2026-10-09",
  "reminder_times": ["08:00", "20:00"],
  "quantity": 10
}
```

If reminder times are omitted and a common `1-0-1`-style frequency is recognized, the API supplies suggested defaults and marks the schedule as needing confirmation.

## Safety and delivery limits

OCR uses OCR.space and requires `OCR_SPACE_API_KEY`. OCR and medicine-name correction can be wrong; extracted values always require human review, and OCR never creates a medication plan by itself. The chatbot gives conservative safety guidance and does not diagnose or recommend doses. Refill quantities and days remaining are estimates based on entered quantity, duration, and reminders per day.

The background worker writes medication reminders, missed-dose records, refill alerts, custom reminders, and appointment reminders to the in-app notification table. With the web app open, it polls for alerts and can show browser notifications after the user enables them from the bell menu. Reminder delivery depends on the API process running; this app does not send push notifications while closed, SMS, or email. Browser speech can read medication alerts aloud on request. Language preference is stored; translated interface text is still being added. Before real patient data is used, deploy behind HTTPS, configure private backups and secret management, and add operational rate limiting. Accounts created by the old prototype without a password hash cannot log in; register a new account.
