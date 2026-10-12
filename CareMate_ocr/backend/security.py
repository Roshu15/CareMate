"""Password hashing and revocable opaque bearer sessions."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

SESSION_DAYS = 14


def hash_password(password: str) -> str:
    if len(password) < 10 or len(password) > 256:
        raise HTTPException(422, "Password must be between 10 and 256 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + salt.hex() + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = stored.split("$", 2)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def new_session(db, user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(40)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()
    db.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
               (hashlib.sha256(token.encode()).hexdigest(), user_id, expires))
    return token, expires


def authenticate(db, token: str):
    digest = hashlib.sha256(token.encode()).hexdigest()
    row = db.execute("SELECT u.id,u.name,u.email,u.role,u.phone,u.language,s.expires_at FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
                     (digest,)).fetchone()
    if not row:
        return None
    try:
        expired = datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc)
    except ValueError:
        expired = True
    if expired:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (digest,))
        return None
    return row


def enforce_patient_access(db, user, patient_id: int):
    patient = db.execute("SELECT created_by FROM patients WHERE id=?", (patient_id,)).fetchone()
    if not patient:
        raise HTTPException(404, "Patient not found")
    if user["role"] == "caretaker" and patient["created_by"] == user["id"]:
        return
    if db.execute("SELECT 1 FROM patient_caregivers WHERE patient_id=? AND caregiver_id=?",
                  (patient_id, user["id"])).fetchone():
        return
    raise HTTPException(403, "You do not have access to this patient")


async def auth_middleware(request: Request, call_next):
    path = request.url.path
    public = {"/api/auth/register", "/api/auth/login", "/api/contact", "/api/chat"}
    if not path.startswith("/api/") or path in public or request.method == "OPTIONS":
        return await call_next(request)
    try:
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "Bearer token required")
        from .database import connection
        with connection() as db:
            user = authenticate(db, token)
            if not user:
                raise HTTPException(401, "Session is invalid or expired")
            uid = user["id"]
            segments = path.strip("/").split("/")
            patient_id = None
            if len(segments) >= 3 and segments[1] == "patients":
                try: patient_id = int(segments[2])
                except ValueError: pass
            elif len(segments) >= 3 and segments[1] == "medicines":
                try:
                    med_id = int(segments[2])
                    med = db.execute("SELECT patient_id FROM medicines WHERE id=?", (med_id,)).fetchone()
                    if not med: raise HTTPException(404, "Medicine not found")
                    if med["patient_id"] is None: raise HTTPException(404, "Medicine is not linked to a patient")
                    patient_id = med["patient_id"]
                except ValueError: pass
            elif len(segments) >= 3 and segments[1] == "notifications":
                try:
                    note_id = int(segments[2])
                    note = db.execute("SELECT user_id,patient_id FROM notifications WHERE id=?", (note_id,)).fetchone()
                    if not note: raise HTTPException(404, "Notification not found")
                    if note["user_id"] not in (None, uid): raise HTTPException(403, "Notification belongs to another user")
                    patient_id = note["patient_id"]
                except ValueError: pass
            elif len(segments) >= 3 and segments[1] in {"appointments", "reminders", "prescriptions"}:
                try:
                    item_id=int(segments[2])
                    table=segments[1]
                    item=db.execute(f"SELECT patient_id FROM {table} WHERE id=?",(item_id,)).fetchone()
                    if not item: raise HTTPException(404, f"{table[:-1].capitalize()} not found")
                    patient_id=item["patient_id"]
                except ValueError: pass
            elif len(segments) >= 3 and segments[1] == "caregiver-requests":
                try:
                    request_id=int(segments[2])
                    access=db.execute("SELECT cr.caregiver_id,p.created_by FROM caregiver_requests cr JOIN patients p ON p.id=cr.patient_id WHERE cr.id=?",(request_id,)).fetchone()
                    if not access: raise HTTPException(404,"Caregiver request not found")
                    if uid not in (access["caregiver_id"],access["created_by"]): raise HTTPException(403,"You cannot access this caregiver request")
                except ValueError: pass
            if patient_id:
                enforce_patient_access(db, user, patient_id)
            if len(segments) >= 4 and segments[:2] == ["api", "patients"] and segments[3] == "caregivers":
                owner = db.execute("SELECT created_by FROM patients WHERE id=?", (patient_id,)).fetchone()
                if user["role"] != "caretaker" or not owner or owner["created_by"] != uid:
                    raise HTTPException(403, "Only the caretaker who added the patient can manage caregiver links")
            if segments[:2] == ["api", "patients"] and len(segments) == 2 and request.method == "POST":
                if user["role"] != "caretaker":
                    raise HTTPException(403, "Caretakers have their own profile. Caregivers request access to an existing patient.")
            if segments[:2] == ["api", "users"]:
                if len(segments) == 3:
                    try: target = int(segments[2])
                    except ValueError: target = -1
                    if target != uid: raise HTTPException(403, "You can only update your own profile")
                elif request.method == "GET":
                    raise HTTPException(403, "Use /api/auth/me to view your profile")
            request.state.user = dict(user)
        return await call_next(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)
