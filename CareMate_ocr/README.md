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
$env:OCR_SPACE_API_KEY = "your-ocr-space-api-key"
uvicorn app:app --reload
```

The CareMate web app is served at `http://127.0.0.1:8000/`, API docs are at `/docs`, and `/health` is the health check. Serving the interface and API together avoids separate frontend setup. Set `CAREMATE_CORS_ORIGINS` only if you later host the frontend separately. The API starts its in-app reminder worker automatically. Poll interval defaults to 20 seconds (`CAREMATE_REMINDER_POLL_SECONDS`); dose confirmation grace period defaults to 30 minutes (`CAREMATE_DOSE_GRACE_MINUTES`).

## Install CareMate on a phone

CareMate can be installed as a Progressive Web App (PWA), using the same website and account. Deploy it to an HTTPS address first; browser installation and offline app-shell support require HTTPS (or localhost during development).

- **Android:** Open the CareMate HTTPS address in Chrome, open the browser menu, and choose **Install app** or **Add to Home screen**.
- **iPhone/iPad:** Open the address in Safari, tap **Share**, then **Add to Home Screen**.

The installed app opens in its own window. Its interface shell can load from cache, but signing in, viewing or saving care records, OCR, and reminders require an internet connection to the CareMate service. API responses and patient information are not stored in the offline cache. Background notifications require browser permission and Web Push setup as described below.

### Local notifications while the browser is closed

For local desktop use, CareMate can send system push notifications for scheduled doses while its browser tab is closed. The local FastAPI server must keep running, the computer must stay on and connected to the internet, and browser notifications must be allowed. These use the device's normal notification sound; the operating system can mute or change it. This does not work if you stop the local server.

1. Install dependencies from the activated project virtual environment: `pip install -r requirements.txt`.
2. Generate a stable local Web Push key pair once: `py scripts/generate_vapid_keys.py`. It writes `.local_vapid_keys.json` in the project folder; that file is excluded from Git. Keep it in place and do not share it.
3. Start CareMate and sign in: `uvicorn app:app --reload`.
4. Open `http://127.0.0.1:8000` in Chrome or Edge on the same computer. Open the notification bell and choose **Enable alerts when app is closed**, then allow notifications.
5. Close the CareMate tab to try a dose alert. Leave the terminal running; the reminder worker checks schedules every 20 seconds by default.

The service worker and system notification can run without the tab, but the local reminder worker cannot run if the computer sleeps or the FastAPI server is stopped. On iPhone/iPad, Web Push requires the site to be added to the Home Screen and supported by the installed web app; a local `127.0.0.1` address is only reachable on the device hosting that server.

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
- Notifications and support: `GET /api/notifications`, `PATCH /api/notifications/{id}/read`, `POST /api/contact`, `GET /api/chat/history`, `POST /api/chat`, `GET /api/rxnorm?name=...`. Chat history is private to the signed-in account and assistant replies use its saved English, Hindi, or Marathi preference.

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

The background worker writes medication reminders, missed-dose records, refill alerts, custom reminders, and appointment reminders to the in-app notification table. With the web app open, it polls for alerts and can show browser notifications after the user enables them from the bell menu. The bell menu's alarm sound switch plays a repeating chime while the page is open. Its background-alert switch subscribes the current browser to Web Push, so the device's system notification can sound while the tab is closed, provided the server is running and the device permits notification sound. Do not rely on browser alerts as an emergency or clinically critical alarm. Reminder delivery depends on the API process running; this app does not send SMS or email. Browser speech can read medication alerts aloud on request. Language preference is stored; translated interface text is still being added. Before real patient data is used, deploy behind HTTPS, configure private backups and secret management, and add operational rate limiting. Accounts created by the old prototype without a password hash cannot log in; register a new account.

## Render demo deployment

The `render.yaml` Blueprint defines a free demo web service. Connect this repository in Render and select the root `render.yaml` Blueprint. Add a newly rotated OCR.space key as the `OCR_SPACE_API_KEY` secret in Render; do not commit it to the repository.

This demo stores SQLite data at `/tmp/caremate.db`. Render's free web services can spin down and lose local filesystem data, so use only fictional demo accounts and records. This deployment is not configured for real patient data.
