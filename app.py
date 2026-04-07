# backend/app.py

import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Query, HTTPException, Depends, UploadFile, File, status, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, LineString, mapping
from shapely import wkb
from openlocationcode import openlocationcode as olc
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import json
from passlib.context import CryptContext
from jose import JWTError, jwt
import tempfile
import zipfile
import shutil

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------
# Load environment variables
# -------------------------------
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    logger.warning("SECRET_KEY not set. Using default (not secure for production)")
    SECRET_KEY = "replace_this_with_a_secure_random_key_in_production"

ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 120))

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
FRONTEND_URL = os.getenv("FRONTEND_URL", "")
if FRONTEND_URL:
    ALLOWED_ORIGINS.append(FRONTEND_URL)

GEOCODING_TIMEOUT = int(os.getenv("GEOCODING_TIMEOUT", 5))
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# -------------------------------
# Database connection
# -------------------------------
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    echo=ENVIRONMENT == "development"
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# -------------------------------
# FastAPI App
# -------------------------------
app = FastAPI(
    title="Wastewater GIS Backend",
    version="2.0.0",
    description="Complete backend for wastewater management system",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# -------------------------------
# Geocoding (optional)
# -------------------------------
try:
    geolocator = Nominatim(user_agent="wastewater_gis_app", timeout=GEOCODING_TIMEOUT)
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
except Exception as e:
    logger.error(f"Geocoding init failed: {e}")
    geolocator = None
    geocode = None

# -------------------------------
# Auth helpers
# -------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def get_password_hash(password):
    return pwd_context.hash(password)

def authenticate_user(email: str, password: str):
    try:
        query = text("SELECT * FROM profiles WHERE email = :email")
        user = engine.execute(query, {"email": email}).fetchone()
        if user and verify_password(password, user.password_hash):
            return user
        return None
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return None

def create_access_token(data: dict, expires_delta=None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    query = text("SELECT * FROM profiles WHERE email = :email")
    user = engine.execute(query, {"email": email}).fetchone()
    if user is None:
        raise credentials_exception
    return user

def require_role(roles: List[str]):
    def role_checker(current_user = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker

# -------------------------------
# Helper functions
# -------------------------------
def geom_to_geojson(geom_bytes):
    if geom_bytes is None:
        return None
    try:
        shape = wkb.loads(geom_bytes)
        return mapping(shape)
    except:
        return None

def get_plus_code_from_coordinates(lat: float, lng: float) -> str:
    try:
        return olc.encode(lat, lng, code_length=10)
    except:
        return None

# -------------------------------
# Startup
# -------------------------------
@app.on_event("startup")
def startup_event():
    logger.info("Starting Wastewater GIS Backend v2")
    # Optionally create tables here

# -------------------------------
# Health & Info
# -------------------------------
@app.get("/health")
def health_check():
    try:
        engine.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    return {"status": "healthy", "database": db_status, "environment": ENVIRONMENT}

@app.get("/api/info")
def service_info(current_user = Depends(get_current_user)):
    return {
        "allowed_origins": ALLOWED_ORIGINS,
        "tables": inspect(engine).get_table_names(),
        "plus_code_support": True,
        "geocoding_available": geolocator is not None,
        "user_role": current_user.role
    }

# -------------------------------
# Authentication endpoints
# -------------------------------
@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/me")
def get_me(current_user = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "name": getattr(current_user, 'full_name', None),
        "is_active": getattr(current_user, 'is_active', True)
    }

class UserCreate(BaseModel):
    email: str
    password: str
    name: Optional[str] = None
    role: str

@app.post("/api/register", status_code=201)
def register(user: UserCreate):
    hashed = get_password_hash(user.password)
    query = text("""
        INSERT INTO profiles (email, password_hash, full_name, role, is_active)
        VALUES (:email, :pwd, :name, :role, false)
        RETURNING id
    """)
    try:
        result = engine.execute(query, {
            "email": user.email,
            "pwd": hashed,
            "name": user.name,
            "role": user.role
        })
        return {"message": "User created. Awaiting admin approval."}
    except Exception as e:
        raise HTTPException(400, str(e))

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None

@app.put("/api/profile")
def update_profile(profile: ProfileUpdate, current_user = Depends(get_current_user)):
    updates = []
    values = []
    if profile.full_name is not None:
        updates.append("full_name = $1")
        values.append(profile.full_name)
    if profile.phone is not None:
        updates.append("phone = $2")
        values.append(profile.phone)
    if profile.department is not None:
        updates.append("department = $3")
        values.append(profile.department)
    if not updates:
        return {"message": "No fields to update"}
    values.append(current_user.id)
    query = f"UPDATE profiles SET {', '.join(updates)} WHERE id = ${len(values)}"
    engine.execute(text(query), values)
    return {"message": "Profile updated"}

# -------------------------------
# Manholes (CRUD)
# -------------------------------
@app.get("/api/manholes")
def get_manholes(current_user = Depends(get_current_user)):
    rows = engine.execute(text("SELECT * FROM waste_water_manhole ORDER BY gid"))
    result = []
    for row in rows:
        d = dict(row)
        if d.get('geom'):
            d['geom'] = geom_to_geojson(d['geom'])
        result.append(d)
    return result

@app.get("/api/manholes/{gid}")
def get_manhole(gid: int, current_user = Depends(get_current_user)):
    row = engine.execute(text("SELECT * FROM waste_water_manhole WHERE gid = :gid"), {"gid": gid}).fetchone()
    if not row:
        raise HTTPException(404, "Manhole not found")
    d = dict(row)
    if d.get('geom'):
        d['geom'] = geom_to_geojson(d['geom'])
    return d

@app.post("/api/manholes", status_code=201)
def create_manhole(manhole: Dict[str, Any], current_user = Depends(require_role(['engineer']))):
    # Simplified: expects geom as GeoJSON Point
    geom = manhole.get('geom')
    if not geom:
        raise HTTPException(400, "Geometry required")
    point = Point(geom['coordinates'][0], geom['coordinates'][1])
    wkb_geom = point.wkb
    query = text("""
        INSERT INTO waste_water_manhole (manhole_id, geom, plus_code, created_at)
        VALUES (:mid, ST_GeomFromWKB(:geom, 4326), :plus_code, now())
        RETURNING gid
    """)
    plus_code = get_plus_code_from_coordinates(point.y, point.x)
    result = engine.execute(query, {
        "mid": manhole.get('manhole_id'),
        "geom": wkb_geom,
        "plus_code": plus_code
    })
    return {"gid": result.fetchone()[0]}

@app.put("/api/manholes/{gid}")
def update_manhole(gid: int, data: Dict[str, Any], current_user = Depends(require_role(['engineer']))):
    # Build dynamic update
    set_clauses = []
    values = []
    i = 1
    for key, val in data.items():
        if key == 'geom' and val:
            point = Point(val['coordinates'][0], val['coordinates'][1])
            set_clauses.append(f"geom = ST_GeomFromWKB(${i}, 4326)")
            values.append(point.wkb)
            i += 1
        else:
            set_clauses.append(f"{key} = ${i}")
            values.append(val)
            i += 1
    if not set_clauses:
        raise HTTPException(400, "No fields to update")
    values.append(gid)
    query = f"UPDATE waste_water_manhole SET {', '.join(set_clauses)} WHERE gid = ${i}"
    engine.execute(text(query), values)
    return {"message": "Updated"}

@app.delete("/api/manholes/{gid}")
def delete_manhole(gid: int, current_user = Depends(require_role(['engineer']))):
    engine.execute(text("DELETE FROM waste_water_manhole WHERE gid = :gid"), {"gid": gid})
    return {"message": "Deleted"}

# -------------------------------
# Pipelines (similar, abbreviated for brevity)
# -------------------------------
@app.get("/api/pipelines")
def get_pipelines(current_user = Depends(get_current_user)):
    rows = engine.execute(text("SELECT * FROM waste_water_pipeline ORDER BY gid"))
    result = []
    for row in rows:
        d = dict(row)
        if d.get('geom'):
            d['geom'] = geom_to_geojson(d['geom'])
        result.append(d)
    return result

@app.get("/api/pipelines/{gid}")
def get_pipeline(gid: int, current_user = Depends(get_current_user)):
    row = engine.execute(text("SELECT * FROM waste_water_pipeline WHERE gid = :gid"), {"gid": gid}).fetchone()
    if not row:
        raise HTTPException(404, "Pipeline not found")
    d = dict(row)
    if d.get('geom'):
        d['geom'] = geom_to_geojson(d['geom'])
    return d

@app.put("/api/pipelines/{gid}")
def update_pipeline(gid: int, data: Dict[str, Any], current_user = Depends(require_role(['engineer']))):
    # Similar dynamic update as manholes
    set_clauses = []
    values = []
    i = 1
    for key, val in data.items():
        if key == 'geom' and val:
            point = Point(val['coordinates'][0], val['coordinates'][1])
            set_clauses.append(f"geom = ST_GeomFromWKB(${i}, 4326)")
            values.append(point.wkb)
            i += 1
        else:
            set_clauses.append(f"{key} = ${i}")
            values.append(val)
            i += 1
    if not set_clauses:
        raise HTTPException(400, "No fields to update")
    values.append(gid)
    query = f"UPDATE waste_water_pipeline SET {', '.join(set_clauses)} WHERE gid = ${i}"
    engine.execute(text(query), values)
    return {"message": "Updated"}

# -------------------------------
# Forms (engineer only)
# -------------------------------
class FormCreate(BaseModel):
    title: str
    description: Optional[str] = None

class FieldCreate(BaseModel):
    label: str
    field_type: str
    options: Optional[List[str]] = None
    required: bool = False

@app.post("/api/forms", status_code=201)
def create_form(form: FormCreate, current_user = Depends(require_role(['engineer']))):
    query = text("INSERT INTO forms (title, description, created_by) VALUES (:title, :desc, :uid) RETURNING id")
    result = engine.execute(query, {"title": form.title, "desc": form.description, "uid": current_user.id})
    form_id = result.fetchone()[0]
    return {"id": form_id}

@app.get("/api/forms")
def get_forms(current_user = Depends(get_current_user)):
    if current_user.role == 'engineer':
        rows = engine.execute(text("SELECT * FROM forms ORDER BY created_at DESC"))
    else:
        rows = engine.execute(text("SELECT * FROM forms WHERE is_active = true ORDER BY created_at DESC"))
    return [dict(row) for row in rows]

@app.put("/api/forms/{form_id}")
def update_form(form_id: str, form: FormCreate, current_user = Depends(require_role(['engineer']))):
    engine.execute(text("UPDATE forms SET title = :title, description = :desc WHERE id = :id"),
                   {"title": form.title, "desc": form.description, "id": form_id})
    return {"message": "Updated"}

@app.post("/api/forms/{form_id}/fields")
def save_form_fields(form_id: str, fields: List[FieldCreate], current_user = Depends(require_role(['engineer']))):
    engine.execute(text("DELETE FROM form_fields WHERE form_id = :fid"), {"fid": form_id})
    for idx, f in enumerate(fields):
        engine.execute(text("""
            INSERT INTO form_fields (form_id, label, field_type, options, required, order_index)
            VALUES (:fid, :label, :type, :opts, :req, :idx)
        """), {
            "fid": form_id,
            "label": f.label,
            "type": f.field_type,
            "opts": json.dumps(f.options) if f.options else None,
            "req": f.required,
            "idx": idx
        })
    return {"message": f"Saved {len(fields)} fields"}

@app.get("/api/forms/{form_id}/fields")
def get_form_fields(form_id: str, current_user = Depends(get_current_user)):
    rows = engine.execute(text("SELECT * FROM form_fields WHERE form_id = :fid ORDER BY order_index"), {"fid": form_id})
    return [dict(row) for row in rows]

# -------------------------------
# Submissions (collectors)
# -------------------------------
class SubmissionCreate(BaseModel):
    form_id: str
    data: Dict[str, Any]
    location: Optional[Dict[str, float]] = None  # {lat, lng}
    collector_id: str

@app.post("/api/submissions", status_code=201)
def create_submission(sub: SubmissionCreate, current_user = Depends(require_role(['field-collector']))):
    geom_wkb = None
    if sub.location and 'lat' in sub.location and 'lng' in sub.location:
        point = Point(sub.location['lng'], sub.location['lat'])
        geom_wkb = point.wkb
    query = text("""
        INSERT INTO form_submissions (form_id, collector_id, data, location)
        VALUES (:fid, :uid, :data, ST_GeomFromWKB(:geom, 4326))
        RETURNING id
    """)
    result = engine.execute(query, {
        "fid": sub.form_id,
        "uid": sub.collector_id,
        "data": json.dumps(sub.data),
        "geom": geom_wkb
    })
    new_id = result.fetchone()[0]
    return {"id": new_id, "status": "pending"}

@app.get("/api/submissions")
def get_submissions(current_user = Depends(get_current_user)):
    if current_user.role == 'engineer':
        rows = engine.execute(text("SELECT * FROM form_submissions ORDER BY submitted_at DESC"))
    else:
        rows = engine.execute(text("SELECT * FROM form_submissions WHERE collector_id = :uid ORDER BY submitted_at DESC"),
                              {"uid": current_user.id})
    result = []
    for row in rows:
        d = dict(row)
        if d.get('location'):
            d['location'] = geom_to_geojson(d['location'])
        result.append(d)
    return result

@app.put("/api/submissions/{sub_id}")
def update_submission_status(sub_id: str, status_update: Dict[str, str], current_user = Depends(require_role(['engineer']))):
    new_status = status_update.get('status')
    if new_status not in ['approved', 'rejected', 'cleaned']:
        raise HTTPException(400, "Invalid status")
    engine.execute(text("UPDATE form_submissions SET status = :status WHERE id = :id"),
                   {"status": new_status, "id": sub_id})
    return {"message": "Status updated"}

# -------------------------------
# Maintenance Records
# -------------------------------
class MaintenanceCreate(BaseModel):
    feature_type: str
    feature_id: str
    maintenance_type: str
    description: Optional[str] = None
    priority: str = "medium"
    scheduled_date: Optional[str] = None
    technician: Optional[str] = None
    notes: Optional[str] = None

@app.post("/api/maintenance", status_code=201)
def create_maintenance(rec: MaintenanceCreate, current_user = Depends(require_role(['field-operator', 'engineer']))):
    query = text("""
        INSERT INTO maintenance_records
        (feature_type, feature_id, maintenance_type, description, priority,
         scheduled_date, technician, notes, created_by)
        VALUES (:ft, :fid, :mt, :desc, :prio, :sched, :tech, :notes, :uid)
        RETURNING id
    """)
    result = engine.execute(query, {
        "ft": rec.feature_type,
        "fid": rec.feature_id,
        "mt": rec.maintenance_type,
        "desc": rec.description,
        "prio": rec.priority,
        "sched": rec.scheduled_date,
        "tech": rec.technician,
        "notes": rec.notes,
        "uid": current_user.id
    })
    return {"id": result.fetchone()[0], "status": "pending"}

@app.get("/api/maintenance")
def get_maintenance(current_user = Depends(get_current_user)):
    if current_user.role == 'engineer':
        rows = engine.execute(text("SELECT * FROM maintenance_records ORDER BY created_at DESC"))
    else:
        rows = engine.execute(text("SELECT * FROM maintenance_records WHERE created_by = :uid ORDER BY created_at DESC"),
                              {"uid": current_user.id})
    return [dict(row) for row in rows]

@app.put("/api/maintenance/{record_id}/approve")
def approve_maintenance(record_id: int, current_user = Depends(require_role(['engineer']))):
    rec = engine.execute(text("SELECT * FROM maintenance_records WHERE id = :rid"), {"rid": record_id}).fetchone()
    if not rec:
        raise HTTPException(404, "Record not found")
    table = 'waste_water_manhole' if rec.feature_type == 'manhole' else 'waste_water_pipeline'
    id_col = 'gid'
    update_sql = text(f"""
        UPDATE {table}
        SET condition_status = :status,
            inspector = :inspector,
            last_inspection_date = :date
        WHERE {id_col} = :fid
    """)
    engine.execute(update_sql, {
        "status": rec.maintenance_type,
        "inspector": rec.technician,
        "date": rec.scheduled_date,
        "fid": rec.feature_id
    })
    engine.execute(text("""
        UPDATE maintenance_records
        SET status = 'approved', reviewed_by = :uid, reviewed_at = now()
        WHERE id = :rid
    """), {"uid": current_user.id, "rid": record_id})
    return {"message": "Approved"}

# -------------------------------
# Asset Edits (operator proposes edits)
# -------------------------------
class AssetEditCreate(BaseModel):
    feature_type: str
    feature_id: str
    proposed_data: Dict[str, Any]

@app.post("/api/asset-edits", status_code=201)
def create_asset_edit(edit: AssetEditCreate, current_user = Depends(require_role(['field-operator']))):
    query = text("""
        INSERT INTO asset_edits (feature_type, feature_id, proposed_data, created_by)
        VALUES (:ft, :fid, :data, :uid)
        RETURNING id
    """)
    result = engine.execute(query, {
        "ft": edit.feature_type,
        "fid": edit.feature_id,
        "data": json.dumps(edit.proposed_data),
        "uid": current_user.id
    })
    return {"id": result.fetchone()[0], "status": "pending"}

@app.get("/api/asset-edits")
def get_asset_edits(current_user = Depends(get_current_user)):
    if current_user.role == 'engineer':
        rows = engine.execute(text("SELECT * FROM asset_edits WHERE status = 'pending' ORDER BY created_at DESC"))
    else:
        rows = engine.execute(text("SELECT * FROM asset_edits WHERE created_by = :uid AND status = 'pending' ORDER BY created_at DESC"),
                              {"uid": current_user.id})
    return [dict(row) for row in rows]

@app.put("/api/asset-edits/{edit_id}/approve")
def approve_asset_edit(edit_id: int, current_user = Depends(require_role(['engineer']))):
    edit = engine.execute(text("SELECT * FROM asset_edits WHERE id = :eid AND status = 'pending'"), {"eid": edit_id}).fetchone()
    if not edit:
        raise HTTPException(404, "Edit not found")
    table = 'waste_water_manhole' if edit.feature_type == 'manhole' else 'waste_water_pipeline'
    id_col = 'gid'
    proposed = json.loads(edit.proposed_data)
    set_clauses = []
    values = []
    i = 1
    for key, val in proposed.items():
        if key == 'geom' and isinstance(val, dict):
            point = Point(val['coordinates'][0], val['coordinates'][1])
            set_clauses.append(f"geom = ST_GeomFromWKB(${i}, 4326)")
            values.append(point.wkb)
            i += 1
        else:
            set_clauses.append(f"{key} = ${i}")
            values.append(val)
            i += 1
    if not set_clauses:
        raise HTTPException(400, "No fields to update")
    values.append(edit.feature_id)
    update_sql = f"UPDATE {table} SET {', '.join(set_clauses)} WHERE {id_col} = ${i}"
    engine.execute(text(update_sql), values)
    engine.execute(text("UPDATE asset_edits SET status = 'approved', reviewed_by = :uid, reviewed_at = now() WHERE id = :eid"),
                   {"uid": current_user.id, "eid": edit_id})
    return {"message": "Approved"}

@app.put("/api/asset-edits/{edit_id}/reject")
def reject_asset_edit(edit_id: int, current_user = Depends(require_role(['engineer']))):
    result = engine.execute(text("UPDATE asset_edits SET status = 'rejected', reviewed_by = :uid, reviewed_at = now() WHERE id = :eid"),
                            {"uid": current_user.id, "eid": edit_id})
    if result.rowcount == 0:
        raise HTTPException(404, "Edit not found")
    return {"message": "Rejected"}

# -------------------------------
# Flags
# -------------------------------
class FlagCreate(BaseModel):
    feature_type: str
    feature_id: str
    reason: str
    severity: str = "medium"
    notes: Optional[str] = None

@app.post("/api/flags", status_code=201)
def create_flag(flag: FlagCreate, current_user = Depends(require_role(['field-collector', 'engineer']))):
    query = text("""
        INSERT INTO flags (feature_type, feature_id, reason, severity, notes, reported_by)
        VALUES (:ft, :fid, :reason, :sev, :notes, :uid)
        RETURNING id
    """)
    result = engine.execute(query, {
        "ft": flag.feature_type,
        "fid": flag.feature_id,
        "reason": flag.reason,
        "sev": flag.severity,
        "notes": flag.notes,
        "uid": current_user.id
    })
    return {"id": result.fetchone()[0]}

@app.get("/api/flags")
def get_flags(current_user = Depends(get_current_user)):
    if current_user.role == 'engineer':
        rows = engine.execute(text("SELECT * FROM flags ORDER BY created_at DESC"))
    else:
        rows = engine.execute(text("SELECT * FROM flags WHERE reported_by = :uid ORDER BY created_at DESC"),
                              {"uid": current_user.id})
    return [dict(row) for row in rows]

@app.put("/api/flags/{flag_id}/resolve")
def resolve_flag(flag_id: int, current_user = Depends(require_role(['engineer']))):
    engine.execute(text("UPDATE flags SET resolved = true WHERE id = :id"), {"id": flag_id})
    return {"message": "Resolved"}

# -------------------------------
# Projects
# -------------------------------
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None

@app.post("/api/projects", status_code=201)
def create_project(proj: ProjectCreate, current_user = Depends(require_role(['engineer']))):
    query = text("INSERT INTO projects (name, description, created_by) VALUES (:name, :desc, :uid) RETURNING id")
    result = engine.execute(query, {"name": proj.name, "desc": proj.description, "uid": current_user.id})
    return {"id": result.fetchone()[0]}

@app.get("/api/projects")
def get_projects(current_user = Depends(get_current_user)):
    rows = engine.execute(text("SELECT * FROM projects ORDER BY created_at DESC"))
    return [dict(row) for row in rows]

@app.put("/api/projects/{proj_id}")
def update_project(proj_id: str, proj: ProjectCreate, current_user = Depends(require_role(['engineer']))):
    engine.execute(text("UPDATE projects SET name = :name, description = :desc WHERE id = :id"),
                   {"name": proj.name, "desc": proj.description, "id": proj_id})
    return {"message": "Updated"}

# -------------------------------
# Shapefile Upload
# -------------------------------
@app.post("/api/upload/shapefile")
async def upload_shapefile(
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    layer_type: str = Form(...),  # "manhole" or "pipeline"
    current_user = Depends(require_role(['engineer']))
):
    suffix = file.filename.split('.')[-1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix}") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name
    try:
        if suffix == 'zip':
            with zipfile.ZipFile(tmp_path, 'r') as zf:
                shp_name = None
                for name in zf.namelist():
                    if name.lower().endswith('.shp'):
                        shp_name = name
                        break
                if not shp_name:
                    raise HTTPException(400, "No .shp file in zip")
                extract_dir = tempfile.mkdtemp()
                zf.extractall(extract_dir)
                shp_path = os.path.join(extract_dir, shp_name)
        else:
            shp_path = tmp_path
        gdf = gpd.read_file(shp_path)
        if gdf.crs is not None and gdf.crs.to_string() != 'EPSG:4326':
            gdf = gdf.to_crs('EPSG:4326')
        inserted = 0
        for _, row in gdf.iterrows():
            geom = row.geometry
            if geom is None:
                continue
            if geom.geom_type != 'Point' and layer_type == 'manhole':
                geom = geom.centroid
            if geom.geom_type != 'LineString' and layer_type == 'pipeline':
                geom = geom.centroid  # fallback
            lng, lat = geom.x, geom.y
            plus_code = get_plus_code_from_coordinates(lat, lng)
            # Get ID from shapefile attributes
            fid = None
            for col in ['id', 'ID', 'manhole_id', 'pipe_id', 'gid']:
                if col in row:
                    fid = row[col]
                    break
            if not fid:
                fid = f"imported_{uuid.uuid4().hex[:8]}"
            if layer_type == 'manhole':
                sql = text("""
                    INSERT INTO waste_water_manhole (manhole_id, geom, plus_code, project_id)
                    VALUES (:id, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), :plus_code, :proj_id)
                    ON CONFLICT (manhole_id) DO UPDATE
                    SET geom = EXCLUDED.geom, plus_code = EXCLUDED.plus_code, project_id = EXCLUDED.project_id
                """)
            else:
                sql = text("""
                    INSERT INTO waste_water_pipeline (pipe_id, geom, plus_code, project_id)
                    VALUES (:id, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326), :plus_code, :proj_id)
                    ON CONFLICT (pipe_id) DO UPDATE
                    SET geom = EXCLUDED.geom, plus_code = EXCLUDED.plus_code, project_id = EXCLUDED.project_id
                """)
            engine.execute(sql, {
                "id": str(fid),
                "lng": lng,
                "lat": lat,
                "plus_code": plus_code,
                "proj_id": project_id
            })
            inserted += 1
        return {"message": f"Imported {inserted} features", "features": inserted}
    except Exception as e:
        logger.error(f"Shapefile upload error: {e}")
        raise HTTPException(500, str(e))
    finally:
        os.unlink(tmp_path)
        if 'extract_dir' in locals():
            shutil.rmtree(extract_dir)

# -------------------------------
# Access Requests
# -------------------------------
class AccessRequest(BaseModel):
    email: str
    role_requested: str

@app.post("/api/access-requests", status_code=201)
def create_access_request(req: AccessRequest):
    query = text("""
        INSERT INTO access_requests (email, role_requested, status, created_at)
        VALUES (:email, :role, 'Waiting', now())
    """)
    engine.execute(query, {"email": req.email, "role": req.role_requested})
    return {"message": "Request submitted"}

# -------------------------------
# Collector Schema (for DataCollection component)
# -------------------------------
@app.get("/api/collector-schema")
def get_collector_schema(mode: str = Query(...), current_user = Depends(require_role(['field-collector']))):
    # Return dummy schema or fetch from a table; here we return a static example
    if mode == 'manhole':
        return [
            {"id": 1, "label": "Manhole ID", "type": "text", "required": True},
            {"id": 2, "label": "Depth (m)", "type": "number", "required": False},
            {"id": 3, "label": "Condition", "type": "select", "options": ["Good", "Fair", "Poor"], "required": True}
        ]
    elif mode == 'pipeline':
        return [
            {"id": 1, "label": "Pipe ID", "type": "text", "required": True},
            {"id": 2, "label": "Material", "type": "select", "options": ["PVC", "Concrete", "Steel"], "required": False},
            {"id": 3, "label": "Diameter (mm)", "type": "number", "required": False}
        ]
    else:
        return []

# -------------------------------
# Root
# -------------------------------
@app.get("/")
def root():
    return {
        "name": "Wastewater GIS Backend",
        "version": "2.0.0",
        "status": "running",
        "docs_url": "/api/docs"
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
