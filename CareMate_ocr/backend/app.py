"""CareMate backend API. Run from this directory with: uvicorn app:app --reload"""
import json
import os
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import database as store
from .medicine_extractor import extract_medicines
from .ocr import extract_text
from .schedule_generation import generate_schedule
from .security import auth_middleware, hash_password, new_session, verify_password
from .reminder_worker import run_reminder_worker, _notify

@asynccontextmanager
async def lifespan(_app):
    worker = asyncio.create_task(run_reminder_worker())
    try:
        yield
    finally:
        worker.cancel()
        try: await worker
        except asyncio.CancelledError: pass

app = FastAPI(title="CareMate API", version="1.0.0", description="Medication support backend. Not a substitute for professional medical advice.", lifespan=lifespan)
origins = [x.strip() for x in os.getenv("CAREMATE_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.middleware("http")(auth_middleware)
SUPPORTED_LANGUAGES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}


class UserIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str
    role: str
    phone: Optional[str] = None
    language: str = "en"
    password: str = Field(min_length=10, max_length=256)

class LoginIn(BaseModel):
    email: str
    password: str

class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=256)

class PatientIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    date_of_birth: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[int] = None
    caregiver_ids: list[int] = Field(default_factory=list)

class CaregiverRequestIn(BaseModel):
    caretaker_email: str

class MedicineIn(BaseModel):
    medicine_name: str
    dose: str = ""
    frequency: str = ""
    timing: str = ""
    duration: int = Field(default=0, ge=0, le=3650)
    start_date: str = Field(default_factory=lambda: date.today().isoformat())
    reminder_times: list[str] = []
    quantity: Optional[float] = Field(default=None, ge=0)
    rxcui: Optional[str] = None

class DoseIn(BaseModel):
    scheduled_date: str
    scheduled_time: str
    status: str
    note: Optional[str] = None

class AppointmentIn(BaseModel):
    title: str = "Doctor follow-up"
    doctor: Optional[str] = None
    appointment_at: str
    notes: Optional[str] = None

class ReminderIn(BaseModel):
    title: str
    body: str = ""
    remind_at: str
    kind: str = "custom"

class ContactIn(BaseModel):
    name: str
    email: str
    message: str = Field(min_length=1, max_length=5000)

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def normalize_datetime(value: str) -> str:
    if not isinstance(value,str):
        raise HTTPException(422,"Use an ISO 8601 date and time, for example 2026-10-09T18:30:00")
    try:
        parsed=datetime.fromisoformat(value.replace("Z","+00:00"))
    except (TypeError,ValueError):
        raise HTTPException(422,"Use an ISO 8601 date and time, for example 2026-10-09T18:30:00")
    return parsed.astimezone().isoformat(timespec="seconds")


def rowdict(row):
    return dict(row) if row else None

def require_patient(db, patient_id):
    row = db.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Patient not found")
    return row

def parse_times(raw):
    try:
        times = json.loads(raw or "[]")
        if not isinstance(times, list): return []
    except (ValueError, TypeError):
        times = [x.strip() for x in (raw or "").split(",") if x.strip()]
    normalized=[]
    for value in times:
        try: normalized.append(datetime.strptime(value,"%I:%M %p").strftime("%H:%M"))
        except (ValueError,TypeError): normalized.append(value)
    return normalized


@app.get("/health")
def health():
    return {"status": "ok", "service": "CareMate API"}

@app.get("/api/languages")
def supported_languages():
    return [{"code":code,"name":name} for code,name in SUPPORTED_LANGUAGES.items()]

@app.post("/api/auth/register", status_code=201)
def register_user(payload: UserIn):
    if payload.role not in ("caretaker", "caregiver"):
        raise HTTPException(422, "role must be caretaker or caregiver")
    if payload.language not in SUPPORTED_LANGUAGES: raise HTTPException(422,"Unsupported language code")
    with store.connection() as db:
        try:
            cur = db.execute("INSERT INTO users(name,email,role,phone,language,password_hash) VALUES(?,?,?,?,?,?)",
                (payload.name,payload.email.lower(),payload.role,payload.phone,payload.language,hash_password(payload.password)))
        except Exception as exc:
            if "UNIQUE" in str(exc): raise HTTPException(409, "Email already exists")
            raise
        user = rowdict(db.execute("SELECT id,name,email,role,phone,language FROM users WHERE id=?",(cur.lastrowid,)).fetchone())
        token, expires = new_session(db, cur.lastrowid)
        if payload.role=="caretaker":
            db.execute("INSERT INTO patients(name,phone,created_by) VALUES(?,?,?)",(payload.name,payload.phone,cur.lastrowid))
        return {"user":user,"access_token":token,"token_type":"bearer","expires_at":expires}

@app.post("/api/auth/login")
def login(payload: LoginIn):
    with store.connection() as db:
        user = db.execute("SELECT * FROM users WHERE email=?",(payload.email.lower(),)).fetchone()
        if not user or not user["password_hash"] or not verify_password(payload.password,user["password_hash"]):
            raise HTTPException(401,"Email or password is incorrect")
        token, expires = new_session(db,user["id"])
        public_user={k:user[k] for k in ("id","name","email","role","phone","language")}
        return {"user":public_user,"access_token":token,"token_type":"bearer","expires_at":expires}

@app.get("/api/auth/me")
def current_user(request: Request):
    user=request.state.user
    if user["role"]=="caretaker":
        with store.connection() as db:
            own=db.execute("SELECT id FROM patients WHERE created_by=? ORDER BY id LIMIT 1",(user["id"],)).fetchone()
            if not own:
                orphan=db.execute("SELECT p.id FROM patients p WHERE p.created_by IS NULL AND NOT EXISTS (SELECT 1 FROM patient_caregivers pc WHERE pc.patient_id=p.id) ORDER BY p.id LIMIT 1").fetchone()
                if orphan: db.execute("UPDATE patients SET created_by=? WHERE id=?",(user["id"],orphan["id"]))
                else: db.execute("INSERT INTO patients(name,created_by) VALUES(?,?)",(user["name"],user["id"]))
    return {k:user[k] for k in ("id","name","email","role","phone","language")}

@app.post("/api/auth/logout",status_code=204)
def logout(request: Request):
    token=request.headers.get("authorization","").partition(" ")[2]
    with store.connection() as db:
        import hashlib
        db.execute("DELETE FROM sessions WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),))

@app.post("/api/auth/change-password", status_code=204)
def change_password(payload:ChangePasswordIn,request:Request):
    token=request.headers.get("authorization","").partition(" ")[2]
    import hashlib
    with store.connection() as db:
        row=db.execute("SELECT password_hash FROM users WHERE id=?",(request.state.user["id"],)).fetchone()
        if not row or not verify_password(payload.current_password,row["password_hash"]):
            raise HTTPException(401,"Current password is incorrect")
        db.execute("UPDATE users SET password_hash=? WHERE id=?",(hash_password(payload.new_password),request.state.user["id"]))
        db.execute("DELETE FROM sessions WHERE user_id=?",(request.state.user["id"],))

@app.post("/api/users", status_code=201)
def create_user(payload: UserIn):
    raise HTTPException(405,"Use /api/auth/register to create an account")

@app.get("/api/users")
def list_users(role: Optional[str] = None):
    raise HTTPException(403,"Use /api/auth/me to view your profile")

@app.patch("/api/users/{user_id}")
def update_user(user_id: int, payload: dict):
    allowed = {"name", "phone", "language"}
    values = {k:v for k,v in payload.items() if k in allowed}
    if not values: raise HTTPException(400, "No editable fields provided")
    if "language" in values and values["language"] not in SUPPORTED_LANGUAGES: raise HTTPException(422,"Unsupported language code")
    with store.connection() as db:
        if not db.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone(): raise HTTPException(404,"User not found")
        db.execute("UPDATE users SET " + ",".join(f"{k}=?" for k in values) + " WHERE id=?", (*values.values(),user_id))
        return rowdict(db.execute("SELECT * FROM users WHERE id=?",(user_id,)).fetchone())

@app.post("/api/patients", status_code=201)
def create_patient(payload: PatientIn, request: Request):
    with store.connection() as db:
        user=request.state.user
        if user["role"]!="caretaker": raise HTTPException(403,"Patients create their own profile when they register. Ask them to connect you as a caregiver.")
        if db.execute("SELECT id FROM patients WHERE created_by=?",(user["id"],)).fetchone(): raise HTTPException(409,"Your caretaker account already has a patient profile. Edit that profile instead.")
        created_by=user["id"]
        cur = db.execute("INSERT INTO patients(name,date_of_birth,phone,notes,created_by) VALUES(?,?,?,?,?)",
                         (payload.name,payload.date_of_birth,payload.phone,payload.notes,created_by))
        pid = cur.lastrowid
        if user["role"]=="caregiver":
            db.execute("INSERT INTO patient_caregivers(patient_id,caregiver_id) VALUES(?,?)",(pid,user["id"]))
        for uid in payload.caregiver_ids:
            if not db.execute("SELECT id FROM users WHERE id=? AND role='caregiver'",(uid,)).fetchone(): raise HTTPException(422,f"Caregiver {uid} not found")
            db.execute("INSERT INTO patient_caregivers(patient_id,caregiver_id) VALUES(?,?)",(pid,uid))
        return rowdict(db.execute("SELECT * FROM patients WHERE id=?",(pid,)).fetchone())

@app.get("/api/patients")
def list_patients(request: Request):
    user=request.state.user
    with store.connection() as db:
        if user["role"] == "caregiver":
            rows = db.execute("SELECT p.* FROM patients p JOIN patient_caregivers pc ON pc.patient_id=p.id WHERE pc.caregiver_id=? ORDER BY p.name",(user["id"],)).fetchall()
        else:
            rows = db.execute("SELECT * FROM patients WHERE created_by=? ORDER BY name",(user["id"],)).fetchall()
        return [rowdict(r) for r in rows]

@app.get("/api/caregivers")
def list_caregivers(request:Request):
    if request.state.user["role"]!="caretaker": raise HTTPException(403,"Only caretakers can connect caregivers")
    with store.connection() as db:
        return [rowdict(r) for r in db.execute("SELECT id,name,email FROM users WHERE role='caregiver' ORDER BY name").fetchall()]

@app.post("/api/caregiver-requests",status_code=201)
def request_patient_access(payload:CaregiverRequestIn,request:Request):
    user=request.state.user
    if user["role"]!="caregiver": raise HTTPException(403,"Only caregiver accounts can request patient access")
    with store.connection() as db:
        caretaker=db.execute("SELECT id,name FROM users WHERE email=? AND role='caretaker'",(payload.caretaker_email.lower(),)).fetchone()
        if not caretaker: raise HTTPException(404,"No caretaker account found for that email")
        patient=db.execute("SELECT id FROM patients WHERE created_by=? ORDER BY id LIMIT 1",(caretaker["id"],)).fetchone()
        if not patient: raise HTTPException(404,"This caretaker does not have a patient profile yet")
        existing=db.execute("SELECT id,status FROM caregiver_requests WHERE patient_id=? AND caregiver_id=?",(patient["id"],user["id"])).fetchone()
        if existing and existing["status"]=="accepted": raise HTTPException(409,"You already have access to this patient")
        if existing:
            db.execute("UPDATE caregiver_requests SET status='pending',updated_at=CURRENT_TIMESTAMP WHERE id=?",(existing["id"],)); request_id=existing["id"]
        else:
            cur=db.execute("INSERT INTO caregiver_requests(patient_id,caregiver_id) VALUES(?,?)",(patient["id"],user["id"])); request_id=cur.lastrowid
        db.execute("INSERT OR IGNORE INTO notifications(patient_id,user_id,title,body,kind,dedupe_key) VALUES(?,?,?,?,?,?)",
                   (patient["id"],caretaker["id"],"Caregiver access requested",f"{user['name']} would like to join your care team.","caregiver_request",f"caregiver-request:{request_id}:pending"))
        return {"id":request_id,"patient_id":patient["id"],"status":"pending"}

@app.get("/api/caregiver-requests")
def list_caregiver_requests(request:Request):
    user=request.state.user
    with store.connection() as db:
        if user["role"]=="caretaker":
            rows=db.execute("SELECT cr.id,cr.patient_id,cr.caregiver_id,cr.status,cr.created_at,u.name AS caregiver_name,u.email AS caregiver_email FROM caregiver_requests cr JOIN patients p ON p.id=cr.patient_id JOIN users u ON u.id=cr.caregiver_id WHERE p.created_by=? ORDER BY cr.created_at DESC",(user["id"],)).fetchall()
        else:
            rows=db.execute("SELECT cr.id,cr.patient_id,cr.caregiver_id,cr.status,cr.created_at,p.name AS patient_name,u.email AS caretaker_email FROM caregiver_requests cr JOIN patients p ON p.id=cr.patient_id JOIN users u ON u.id=p.created_by WHERE cr.caregiver_id=? ORDER BY cr.created_at DESC",(user["id"],)).fetchall()
        return [rowdict(r) for r in rows]

@app.patch("/api/caregiver-requests/{request_id}")
def decide_caregiver_request(request_id:int,payload:dict,request:Request):
    decision=payload.get("status")
    if decision not in ("accepted","declined"): raise HTTPException(422,"status must be accepted or declined")
    user=request.state.user
    if user["role"]!="caretaker": raise HTTPException(403,"Only the patient can approve or decline caregiver access")
    with store.connection() as db:
        row=db.execute("SELECT cr.*,p.created_by FROM caregiver_requests cr JOIN patients p ON p.id=cr.patient_id WHERE cr.id=?",(request_id,)).fetchone()
        if not row: raise HTTPException(404,"Caregiver request not found")
        if row["created_by"]!=user["id"]: raise HTTPException(403,"This request is not for your patient profile")
        db.execute("UPDATE caregiver_requests SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(decision,request_id))
        if decision=="accepted": db.execute("INSERT OR IGNORE INTO patient_caregivers(patient_id,caregiver_id) VALUES(?,?)",(row["patient_id"],row["caregiver_id"]))
        db.execute("INSERT OR IGNORE INTO notifications(patient_id,user_id,title,body,kind,dedupe_key) VALUES(?,?,?,?,?,?)",
                   (row["patient_id"],row["caregiver_id"],"Caregiver access update",f"Your request was {decision}.","caregiver_request",f"caregiver-request:{request_id}:{decision}"))
        return {"id":request_id,"status":decision}

@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: int):
    with store.connection() as db:
        p = rowdict(require_patient(db, patient_id))
        p["caregivers"] = [rowdict(r) for r in db.execute("SELECT u.id,u.name,u.email,u.phone FROM users u JOIN patient_caregivers pc ON pc.caregiver_id=u.id WHERE pc.patient_id=?",(patient_id,)).fetchall()]
        return p

@app.patch("/api/patients/{patient_id}")
def update_patient(patient_id: int, payload: dict):
    allowed = {"name","date_of_birth","phone","notes"}
    values={k:v for k,v in payload.items() if k in allowed}
    if not values: raise HTTPException(400,"No editable fields provided")
    with store.connection() as db:
        require_patient(db,patient_id)
        db.execute("UPDATE patients SET "+",".join(f"{k}=?" for k in values)+" WHERE id=?",(*values.values(),patient_id))
        return rowdict(db.execute("SELECT * FROM patients WHERE id=?",(patient_id,)).fetchone())

@app.put("/api/patients/{patient_id}/caregivers/{caregiver_id}", status_code=204)
def link_caregiver(patient_id: int, caregiver_id: int):
    with store.connection() as db:
        require_patient(db,patient_id)
        if not db.execute("SELECT id FROM users WHERE id=? AND role='caregiver'",(caregiver_id,)).fetchone(): raise HTTPException(404,"Caregiver not found")
        db.execute("INSERT OR IGNORE INTO patient_caregivers(patient_id,caregiver_id) VALUES(?,?)",(patient_id,caregiver_id))

@app.delete("/api/patients/{patient_id}/caregivers/{caregiver_id}", status_code=204)
def unlink_caregiver(patient_id: int, caregiver_id: int):
    with store.connection() as db:
        db.execute("DELETE FROM patient_caregivers WHERE patient_id=? AND caregiver_id=?",(patient_id,caregiver_id))

@app.post("/api/patients/{patient_id}/prescriptions/ocr")
async def upload_prescription(patient_id: int, image: UploadFile = File(...)):
    accepted={"image/jpeg","image/png","image/webp","image/tiff"}
    if image.content_type not in accepted: raise HTTPException(415,"Upload a JPEG, PNG, WEBP, or TIFF image")
    content=await image.read(10*1024*1024+1)
    if len(content)>10*1024*1024: raise HTTPException(413,"Image must be 10 MB or smaller")
    if not content: raise HTTPException(400,"Uploaded image is empty")
    with store.connection() as db: require_patient(db,patient_id)
    try:
        text=extract_text(content,image.filename or "prescription.jpg",image.content_type)
    except Exception as exc:
        if "OCR_SPACE_API_KEY" in str(exc): raise HTTPException(503,str(exc))
        raise HTTPException(502,"OCR provider failed: "+str(exc)[:250])
    if not text.strip(): raise HTTPException(422,"No readable text found in the prescription")
    meds=extract_medicines(text)
    with store.connection() as db:
        cur=db.execute("INSERT INTO prescriptions(patient_id,filename,ocr_text,status) VALUES(?,?,?,?)",
                       (patient_id,image.filename,text,"review_required" if meds else "no_medicines_found"))
        prescription_id=cur.lastrowid
    return {"prescription_id":prescription_id,"ocr_text":text,"medicines":meds,
            "review_required":True,"message":"Check all extracted details against the original prescription with a qualified professional before creating reminders."}

@app.get("/api/patients/{patient_id}/prescriptions")
def list_prescriptions(patient_id:int):
    with store.connection() as db:
        require_patient(db,patient_id)
        return [rowdict(r) for r in db.execute("SELECT id,patient_id,filename,status,created_at FROM prescriptions WHERE patient_id=? ORDER BY id DESC",(patient_id,)).fetchall()]

@app.get("/api/prescriptions/{prescription_id}")
def get_prescription(prescription_id:int,request:Request):
    with store.connection() as db:
        row=db.execute("SELECT * FROM prescriptions WHERE id=?",(prescription_id,)).fetchone()
        if not row: raise HTTPException(404,"Prescription not found")
        from .security import enforce_patient_access
        enforce_patient_access(db,request.state.user,row["patient_id"])
        return rowdict(row)

@app.post("/api/patients/{patient_id}/medicines",status_code=201)
def create_medicine(patient_id:int,payload:MedicineIn,prescription_id:Optional[int]=None):
    suggested = generate_schedule(payload.medicine_name,payload.dose,payload.frequency,payload.timing,payload.duration)["reminder_times"]
    reminder_times=payload.reminder_times or suggested
    for t in reminder_times:
        try: datetime.strptime(t,"%H:%M")
        except ValueError: raise HTTPException(422,f"Invalid reminder time '{t}'; use HH:MM")
    try: date.fromisoformat(payload.start_date)
    except ValueError: raise HTTPException(422,"start_date must use YYYY-MM-DD")
    with store.connection() as db:
        require_patient(db,patient_id)
        if prescription_id and not db.execute("SELECT id FROM prescriptions WHERE id=? AND patient_id=?",(prescription_id,patient_id)).fetchone(): raise HTTPException(404,"Prescription not found")
        cur=db.execute("INSERT INTO medicines(patient_id,prescription_id,medicine_name,dose,frequency,timing,duration,start_date,reminder_times,rxcui,quantity) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (patient_id,prescription_id,payload.medicine_name,payload.dose,payload.frequency,payload.timing,payload.duration,payload.start_date,json.dumps(reminder_times),payload.rxcui,payload.quantity))
        return rowdict(db.execute("SELECT * FROM medicines WHERE id=?",(cur.lastrowid,)).fetchone()) | {"reminder_times":reminder_times,"schedule_needs_confirmation":True}

@app.get("/api/patients/{patient_id}/medicines")
def list_medicines(patient_id:int,active:Optional[bool]=None):
    with store.connection() as db:
        require_patient(db,patient_id)
        rows=db.execute("SELECT * FROM medicines WHERE patient_id=? AND (? IS NULL OR active=?) ORDER BY medicine_name",(patient_id,None if active is None else int(active),None if active is None else int(active))).fetchall()
        return [rowdict(r)|{"reminder_times":parse_times(r["reminder_times"])} for r in rows]

@app.patch("/api/medicines/{medicine_id}")
def update_medicine(medicine_id:int,payload:dict):
    allowed={"medicine_name","dose","frequency","timing","duration","start_date","quantity","active","rxcui"}
    values={k:v for k,v in payload.items() if k in allowed}
    if "reminder_times" in payload:
        for t in payload["reminder_times"]:
            try: datetime.strptime(t,"%H:%M")
            except ValueError: raise HTTPException(422,"Reminder times must use HH:MM")
        values["reminder_times"]=json.dumps(payload["reminder_times"])
    if not values: raise HTTPException(400,"No editable fields provided")
    with store.connection() as db:
        if not db.execute("SELECT id FROM medicines WHERE id=?",(medicine_id,)).fetchone(): raise HTTPException(404,"Medicine not found")
        db.execute("UPDATE medicines SET "+",".join(f"{k}=?" for k in values)+" WHERE id=?",(*values.values(),medicine_id))
        r=rowdict(db.execute("SELECT * FROM medicines WHERE id=?",(medicine_id,)).fetchone()); r["reminder_times"]=parse_times(r["reminder_times"]); return r

@app.delete("/api/medicines/{medicine_id}",status_code=204)
def stop_medicine(medicine_id:int):
    with store.connection() as db:
        cur=db.execute("UPDATE medicines SET active=0 WHERE id=?",(medicine_id,))
        if not cur.rowcount: raise HTTPException(404,"Medicine not found")

@app.post("/api/medicines/{medicine_id}/doses")
def record_dose(medicine_id:int,payload:DoseIn):
    if payload.status.lower() not in ("taken","missed","skipped"): raise HTTPException(422,"status must be taken, missed, or skipped")
    try: date.fromisoformat(payload.scheduled_date); datetime.strptime(payload.scheduled_time,"%H:%M")
    except ValueError: raise HTTPException(422,"Use YYYY-MM-DD scheduled_date and HH:MM scheduled_time")
    with store.connection() as db:
        med=db.execute("SELECT id,medicine_name,dose,patient_id FROM medicines WHERE id=?",(medicine_id,)).fetchone()
        if not med: raise HTTPException(404,"Medicine not found")
        logged=db.execute("SELECT id FROM medication_logs WHERE medicine_id=? AND scheduled_date=? AND scheduled_time=? ORDER BY id DESC LIMIT 1",(medicine_id,payload.scheduled_date,payload.scheduled_time)).fetchone()
        taken_at=datetime.now().isoformat(timespec="seconds") if payload.status.lower()=="taken" else None
        if logged:
            db.execute("UPDATE medication_logs SET status=?,taken_at=?,note=? WHERE id=?",(payload.status.lower(),taken_at,payload.note,logged["id"]))
        else:
            log_columns={r["name"] for r in db.execute("PRAGMA table_info(medication_logs)")}
            if "medicine_name" in log_columns:
                db.execute("INSERT INTO medication_logs(medicine_id,medicine_name,scheduled_date,scheduled_time,status,taken_at,note) VALUES(?,?,?,?,?,?,?)",
                           (medicine_id,med["medicine_name"],payload.scheduled_date,payload.scheduled_time,payload.status.lower(),taken_at,payload.note))
            else:
                db.execute("INSERT INTO medication_logs(medicine_id,scheduled_date,scheduled_time,status,taken_at,note) VALUES(?,?,?,?,?,?)",
                           (medicine_id,payload.scheduled_date,payload.scheduled_time,payload.status.lower(),taken_at,payload.note))
        if payload.status.lower()=="missed":
            _notify(db,med["patient_id"],f"dose:{medicine_id}:{payload.scheduled_date}:{payload.scheduled_time}:missed","Missed medicine dose",
                    f"{med['medicine_name']} ({med['dose']}) was marked missed at {payload.scheduled_time}.","missed_dose")
        return rowdict(db.execute("SELECT * FROM medication_logs WHERE medicine_id=? AND scheduled_date=? AND scheduled_time=? ORDER BY id DESC LIMIT 1",(medicine_id,payload.scheduled_date,payload.scheduled_time)).fetchone())

@app.get("/api/patients/{patient_id}/doses")
def list_doses(patient_id:int,start:Optional[str]=None,end:Optional[str]=None):
    with store.connection() as db:
        require_patient(db,patient_id)
        rows=db.execute("SELECT l.*,m.medicine_name,m.dose FROM medication_logs l JOIN medicines m ON m.id=l.medicine_id WHERE m.patient_id=? AND (? IS NULL OR scheduled_date>=?) AND (? IS NULL OR scheduled_date<=?) ORDER BY scheduled_date DESC,scheduled_time",
                        (patient_id,start,start,end,end)).fetchall()
        return [rowdict(r) for r in rows]

@app.get("/api/patients/{patient_id}/schedule")
def daily_schedule(patient_id:int,on:Optional[str]=None):
    target=on or date.today().isoformat()
    try: day=date.fromisoformat(target)
    except ValueError: raise HTTPException(422,"on must use YYYY-MM-DD")
    with store.connection() as db:
        require_patient(db,patient_id)
        meds=db.execute("SELECT * FROM medicines WHERE patient_id=? AND active=1",(patient_id,)).fetchall()
        items=[]
        for med in meds:
            start=date.fromisoformat(med["start_date"])
            if day<start or (med["duration"] and day>=start+timedelta(days=med["duration"])): continue
            for scheduled_time in parse_times(med["reminder_times"]):
                log=db.execute("SELECT status,taken_at FROM medication_logs WHERE medicine_id=? AND scheduled_date=? AND scheduled_time=?",(med["id"],target,scheduled_time)).fetchone()
                items.append({"medicine_id":med["id"],"medicine_name":med["medicine_name"],"dose":med["dose"],"scheduled_date":target,"scheduled_time":scheduled_time,"status":log["status"] if log else "pending","taken_at":log["taken_at"] if log else None,"timing":med["timing"]})
        return sorted(items,key=lambda item:item["scheduled_time"])

@app.get("/api/patients/{patient_id}/reports/adherence")
def adherence_report(patient_id:int,start:Optional[str]=None,end:Optional[str]=None):
    today=date.today()
    try: from_date=date.fromisoformat(start) if start else today-timedelta(days=29); to_date=date.fromisoformat(end) if end else today
    except ValueError: raise HTTPException(422,"Dates must use YYYY-MM-DD")
    if from_date>to_date: raise HTTPException(422,"start must be on or before end")
    with store.connection() as db:
        require_patient(db,patient_id)
        meds=db.execute("SELECT * FROM medicines WHERE patient_id=? ORDER BY medicine_name",(patient_id,)).fetchall()
        out=[]; total_taken=total_missed=0
        for m in meds:
            logs=db.execute("SELECT status,COUNT(*) n FROM medication_logs WHERE medicine_id=? AND scheduled_date BETWEEN ? AND ? GROUP BY status",(m["id"],from_date.isoformat(),to_date.isoformat())).fetchall()
            counts={r["status"]:r["n"] for r in logs}; taken=counts.get("taken",0); missed=counts.get("missed",0); total_taken+=taken; total_missed+=missed
            start_day=date.fromisoformat(m["start_date"])
            end_day=start_day+timedelta(days=m["duration"]-1) if m["duration"] else to_date
            active_start=max(start_day,from_date); active_end=min(end_day,to_date)
            total_days=max(0,(active_end-active_start).days+1)
            total_doses=total_days*len(parse_times(m["reminder_times"])); logged=taken+missed+counts.get("skipped",0)
            qty=m["quantity"]; times=len(parse_times(m["reminder_times"])); elapsed=max(0,(min(to_date,today)-start_day).days+1); remaining_days=max(0,m["duration"]-elapsed) if m["duration"] else None
            missed_rows=db.execute("SELECT scheduled_date,scheduled_time FROM medication_logs WHERE medicine_id=? AND status='missed' AND scheduled_date BETWEEN ? AND ? ORDER BY scheduled_date,scheduled_time",(m["id"],from_date.isoformat(),to_date.isoformat())).fetchall()
            missed_items=[rowdict(r) for r in missed_rows]
            out.append({"medicine_id":m["id"],"medicine_name":m["medicine_name"],"dose":m["dose"],"taken":taken,"missed":missed,"missed_doses":missed_items,"logged_doses":logged,"expected_doses":total_doses,"adherence_percent":round(taken/(taken+missed)*100,1) if taken+missed else None,"remaining_days":remaining_days,"remaining_quantity":max(0,qty-elapsed*times) if qty is not None else None,"reminder_times":parse_times(m["reminder_times"])})
        summary=[{"medicine_name":item["medicine_name"],"scheduled_date":dose["scheduled_date"],"scheduled_time":dose["scheduled_time"]} for item in out for dose in item["missed_doses"]]
        return {"patient_id":patient_id,"period":{"start":from_date.isoformat(),"end":to_date.isoformat()},"medicines":out,"missed_dose_summary":summary,"total_taken":total_taken,"total_missed":total_missed,"overall_adherence_percent":round(total_taken/(total_taken+total_missed)*100,1) if total_taken+total_missed else None}

@app.post("/api/patients/{patient_id}/appointments",status_code=201)
def create_appointment(patient_id:int,payload:AppointmentIn):
    appointment_at=normalize_datetime(payload.appointment_at)
    with store.connection() as db:
        require_patient(db,patient_id)
        cur=db.execute("INSERT INTO appointments(patient_id,title,doctor,appointment_at,notes) VALUES(?,?,?,?,?)",(patient_id,payload.title,payload.doctor,appointment_at,payload.notes))
        return rowdict(db.execute("SELECT * FROM appointments WHERE id=?",(cur.lastrowid,)).fetchone())

@app.get("/api/patients/{patient_id}/appointments")
def list_appointments(patient_id:int):
    with store.connection() as db:
        require_patient(db,patient_id)
        return [rowdict(r) for r in db.execute("SELECT * FROM appointments WHERE patient_id=? ORDER BY appointment_at",(patient_id,)).fetchall()]

@app.patch("/api/appointments/{appointment_id}")
def update_appointment(appointment_id:int,payload:dict):
    allowed={"title","doctor","appointment_at","notes"}
    values={key:value for key,value in payload.items() if key in allowed}
    if "appointment_at" in values: values["appointment_at"]=normalize_datetime(values["appointment_at"])
    if not values: raise HTTPException(400,"No editable fields provided")
    with store.connection() as db:
        if not db.execute("SELECT id FROM appointments WHERE id=?",(appointment_id,)).fetchone(): raise HTTPException(404,"Appointment not found")
        db.execute("UPDATE appointments SET "+",".join(f"{key}=?" for key in values)+" WHERE id=?",(*values.values(),appointment_id))
        return rowdict(db.execute("SELECT * FROM appointments WHERE id=?",(appointment_id,)).fetchone())

@app.delete("/api/appointments/{appointment_id}",status_code=204)
def delete_appointment(appointment_id:int):
    with store.connection() as db:
        cur=db.execute("DELETE FROM appointments WHERE id=?",(appointment_id,))
        if not cur.rowcount: raise HTTPException(404,"Appointment not found")

@app.post("/api/patients/{patient_id}/reminders",status_code=201)
def create_reminder(patient_id:int,payload:ReminderIn):
    remind_at=normalize_datetime(payload.remind_at)
    with store.connection() as db:
        require_patient(db,patient_id)
        cur=db.execute("INSERT INTO reminders(patient_id,title,body,remind_at,kind) VALUES(?,?,?,?,?)",(patient_id,payload.title,payload.body,remind_at,payload.kind))
        return rowdict(db.execute("SELECT * FROM reminders WHERE id=?",(cur.lastrowid,)).fetchone())

@app.get("/api/patients/{patient_id}/reminders")
def list_reminders(patient_id:int):
    with store.connection() as db:
        require_patient(db,patient_id)
        return [rowdict(r) for r in db.execute("SELECT * FROM reminders WHERE patient_id=? ORDER BY remind_at",(patient_id,)).fetchall()]

@app.patch("/api/reminders/{reminder_id}")
def update_reminder(reminder_id:int,payload:dict):
    allowed={"title","body","remind_at","kind","completed"}
    values={key:value for key,value in payload.items() if key in allowed}
    if "remind_at" in values: values["remind_at"]=normalize_datetime(values["remind_at"])
    if not values: raise HTTPException(400,"No editable fields provided")
    with store.connection() as db:
        if not db.execute("SELECT id FROM reminders WHERE id=?",(reminder_id,)).fetchone(): raise HTTPException(404,"Reminder not found")
        db.execute("UPDATE reminders SET "+",".join(f"{key}=?" for key in values)+" WHERE id=?",(*values.values(),reminder_id))
        return rowdict(db.execute("SELECT * FROM reminders WHERE id=?",(reminder_id,)).fetchone())

@app.delete("/api/reminders/{reminder_id}",status_code=204)
def delete_reminder(reminder_id:int):
    with store.connection() as db:
        cur=db.execute("DELETE FROM reminders WHERE id=?",(reminder_id,))
        if not cur.rowcount: raise HTTPException(404,"Reminder not found")

@app.get("/api/notifications")
def list_notifications(request:Request,patient_id:Optional[int]=None,unread_only:bool=False):
    user=request.state.user
    with store.connection() as db:
        if patient_id is not None:
            from .security import enforce_patient_access
            enforce_patient_access(db,user,patient_id)
        rows=db.execute("SELECT * FROM notifications WHERE user_id=? AND (? IS NULL OR patient_id=?) AND (?=0 OR read=0) ORDER BY created_at DESC",(user["id"],patient_id,patient_id,int(unread_only))).fetchall()
        return [rowdict(r) for r in rows]

@app.patch("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id:int):
    with store.connection() as db:
        cur=db.execute("UPDATE notifications SET read=1 WHERE id=?",(notification_id,))
        if not cur.rowcount: raise HTTPException(404,"Notification not found")
        return {"id":notification_id,"read":True}

@app.post("/api/contact",status_code=201)
def contact(payload:ContactIn):
    with store.connection() as db:
        cur=db.execute("INSERT INTO contact_messages(name,email,message) VALUES(?,?,?)",(payload.name,payload.email,payload.message))
        return {"id":cur.lastrowid,"status":"received"}

@app.post("/api/chat")
def chat(payload:ChatIn):
    message=payload.message.lower()
    urgent=any(x in message for x in ("chest pain","can't breathe","cannot breathe","difficulty breathing","shortness of breath","overdose","suicid","unconscious","severe allergic","allergic reaction","seizure","stroke","heavy bleeding"))
    if urgent:
        return {"reply":"This may be an emergency. Contact your local emergency services or a qualified healthcare professional now. I cannot assess emergencies or provide treatment instructions.","urgent":True,"medical_advice":False}
    return {"reply":"I can help with general medication tracking, but I cannot diagnose conditions, recommend doses, or change a prescription. Check the prescription label and contact your doctor or pharmacist if anything is unclear.","urgent":False,"medical_advice":False}

@app.get("/api/rxnorm")
def rxnorm_lookup(name:str=Query(min_length=1,max_length=120)):
    try:
        import requests
        r=requests.get("https://rxnav.nlm.nih.gov/REST/rxcui.json",params={"name":name},timeout=8); r.raise_for_status()
        ids=r.json().get("idGroup",{}).get("rxnormId",[])
        return {"name":name,"rxcui":ids[0] if ids else None,"matches":ids}
    except Exception: return {"name":name,"rxcui":None,"matches":[],"error":"RxNorm service unavailable"}

@app.get("/api/openapi.json", include_in_schema=False)
def openapi_json(): return app.openapi()

_frontend_dir=os.path.join(os.path.dirname(os.path.dirname(__file__)),"frontend")
app.mount("/static",StaticFiles(directory=_frontend_dir),name="static")
app.mount("/",StaticFiles(directory=_frontend_dir,html=True),name="frontend")
