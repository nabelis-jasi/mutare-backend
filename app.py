# backend/app.py

from fastapi import FastAPI, Query, HTTPException, Depends, UploadFile, File, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, LineString, MultiPoint, MultiLineString
from shapely import wkb
from openlocationcode import openlocationcode as olc
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import requests
import json
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
import uuid
import logging
from typing import Optional, List

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------
# Load environment variables
# -------------------------------
load_dotenv()

# Database URL - handle different formats
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # Replace postgres:// with postgresql:// for SQLAlchemy
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    logger.warning("SECRET_KEY not set in environment variables. Using default (not secure for production)")
    SECRET_KEY = "replace_with_a_secure_random_key_in_production"

ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 120))

# CORS - Allow production domains
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
# Add production frontend URL if provided
FRONTEND_URL = os.getenv("FRONTEND_URL", "")
if FRONTEND_URL:
    ALLOWED_ORIGINS.append(FRONTEND_URL)
    logger.info(f"Added frontend URL to CORS: {FRONTEND_URL}")

GEOCODING_TIMEOUT = int(os.getenv("GEOCODING_TIMEOUT", 5))
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# -------------------------------
# Database connection with connection pooling
# -------------------------------
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

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
# FastAPI App Setup
# -------------------------------
app = FastAPI(
    title="Wastewater GIS Backend", 
    version="1.0.0",
    description="Backend API for Wastewater GIS Management System",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json"
)

# Configure CORS for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# -------------------------------
# Geocoding Setup
# -------------------------------
try:
    geolocator = Nominatim(user_agent="wastewater_gis_app", timeout=GEOCODING_TIMEOUT)
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
    logger.info("Geocoding service initialized")
except Exception as e:
    logger.error(f"Failed to initialize geocoding: {e}")
    geolocator = None
    geocode = None

# -------------------------------
# Auth Setup
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
        if user and hasattr(user, 'password_hash'):
            if verify_password(password, user.password_hash):
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
    
    try:
        query = text("SELECT * FROM profiles WHERE email = :email")
        user = engine.execute(query, {"email": email}).fetchone()
        if user is None:
            raise credentials_exception
        return user
    except Exception as e:
        logger.error(f"Error getting current user: {e}")
        raise credentials_exception

def get_user_role(user_id):
    try:
        query = text("SELECT role FROM profiles WHERE id = :user_id")
        result = engine.execute(query, {"user_id": user_id}).fetchone()
        return result[0] if result else None
    except Exception:
        return None

# -------------------------------
# Database Initialization - Create Plus Code Columns
# -------------------------------

def create_plus_code_columns():
    """Create plus_code column in tables if they don't exist"""
    try:
        # Get database inspector
        inspector = inspect(engine)
        
        # Check if tables exist
        tables = inspector.get_table_names()
        
        # Check and add plus_code to waste_water_manhole
        if 'waste_water_manhole' in tables:
            manhole_columns = [col['name'] for col in inspector.get_columns('waste_water_manhole')]
            if 'plus_code' not in manhole_columns:
                logger.info("Adding plus_code column to waste_water_manhole...")
                engine.execute(text("""
                    ALTER TABLE waste_water_manhole 
                    ADD COLUMN plus_code VARCHAR(20)
                """))
                logger.info("✅ Added plus_code column to waste_water_manhole")
            else:
                logger.info("✅ plus_code column already exists in waste_water_manhole")
        else:
            logger.warning("Table waste_water_manhole does not exist yet")
        
        # Check and add plus_code to waste_water_pipeline
        if 'waste_water_pipeline' in tables:
            pipeline_columns = [col['name'] for col in inspector.get_columns('waste_water_pipeline')]
            if 'plus_code' not in pipeline_columns:
                logger.info("Adding plus_code column to waste_water_pipeline...")
                engine.execute(text("""
                    ALTER TABLE waste_water_pipeline 
                    ADD COLUMN plus_code VARCHAR(20)
                """))
                logger.info("✅ Added plus_code column to waste_water_pipeline")
            else:
                logger.info("✅ plus_code column already exists in waste_water_pipeline")
        else:
            logger.warning("Table waste_water_pipeline does not exist yet")
            
        # Create index for better search performance
        try:
            if 'waste_water_manhole' in tables:
                engine.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_manholes_plus_code 
                    ON waste_water_manhole(plus_code)
                """))
            if 'waste_water_pipeline' in tables:
                engine.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_pipelines_plus_code 
                    ON waste_water_pipeline(plus_code)
                """))
            logger.info("✅ Created indexes on plus_code columns")
        except Exception as e:
            logger.warning(f"Could not create indexes: {e}")
            
    except Exception as e:
        logger.error(f"Error creating plus_code columns: {e}")

# -------------------------------
# Run database initialization on startup
# -------------------------------
@app.on_event("startup")
def startup_event():
    logger.info("🚀 Starting Wastewater GIS Backend...")
    logger.info(f"Environment: {ENVIRONMENT}")
    logger.info(f"Allowed Origins: {ALLOWED_ORIGINS}")
    logger.info("📊 Checking database tables...")
    create_plus_code_columns()
    logger.info("✅ Backend ready!")

# -------------------------------
# Plus Code Helper Functions
# -------------------------------

def get_plus_code_from_coordinates(lat: float, lng: float) -> str:
    """Generate Open Location Code (Plus Code) from coordinates"""
    if lat is None or lng is None:
        return None
    try:
        return olc.encode(lat, lng, code_length=10)
    except Exception as e:
        logger.error(f"Error generating plus code: {e}")
        return None

def get_plus_code_from_address(address: str) -> dict:
    """Get coordinates and plus code from address using geocoding"""
    if geocode is None:
        return {
            "success": False,
            "error": "Geocoding service not available"
        }
    
    try:
        location = geocode(address)
        if location:
            lat = location.latitude
            lng = location.longitude
            plus_code = get_plus_code_from_coordinates(lat, lng)
            return {
                "success": True,
                "address": address,
                "latitude": lat,
                "longitude": lng,
                "plus_code": plus_code,
                "display_name": location.address
            }
        else:
            return {
                "success": False,
                "error": "Address not found"
            }
    except Exception as e:
        logger.error(f"Geocoding error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def get_address_from_plus_code(plus_code: str) -> dict:
    """Get address and coordinates from plus code"""
    if geolocator is None:
        return {
            "success": False,
            "error": "Geocoding service not available"
        }
    
    try:
        decoded = olc.decode(plus_code)
        lat = decoded.latitudeCenter
        lng = decoded.longitudeCenter
        
        location = geolocator.reverse(f"{lat}, {lng}")
        
        return {
            "success": True,
            "plus_code": plus_code,
            "latitude": lat,
            "longitude": lng,
            "address": location.address if location else "Address not found"
        }
    except Exception as e:
        logger.error(f"Plus code decode error: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def update_plus_codes_for_table(table_name: str, id_column: str):
    """Batch update plus codes for all records in a table"""
    try:
        df = pd.read_sql(f"SELECT {id_column}, geom FROM {table_name}", engine)
        updated_count = 0
        
        for _, row in df.iterrows():
            geom = row['geom']
            if geom:
                try:
                    shape = wkb.loads(geom)
                    if shape.geom_type == 'Point':
                        lat = shape.y
                        lng = shape.x
                    else:
                        centroid = shape.centroid
                        lat = centroid.y
                        lng = centroid.x
                    
                    plus_code = get_plus_code_from_coordinates(lat, lng)
                    if plus_code:
                        engine.execute(
                            text(f"UPDATE {table_name} SET plus_code = :plus_code WHERE {id_column} = :id"),
                            {"plus_code": plus_code, "id": row[id_column]}
                        )
                        updated_count += 1
                except Exception as e:
                    logger.error(f"Error processing record {row[id_column]}: {e}")
                    continue
        
        return {"success": True, "updated": updated_count, "total": len(df)}
    except Exception as e:
        logger.error(f"Error updating plus codes for {table_name}: {e}")
        return {"success": False, "error": str(e)}

# -------------------------------
# Helper: Convert geometry to GeoJSON
# -------------------------------
def geom_to_geojson(geom_bytes):
    if geom_bytes is None:
        return None
    try:
        shape = wkb.loads(geom_bytes)
        if shape.is_empty:
            return None
        if shape.geom_type == 'Point':
            return {"type": "Point", "coordinates": [shape.x, shape.y]}
        elif shape.geom_type == 'LineString':
            return {"type": "LineString", "coordinates": list(shape.coords)}
        elif shape.geom_type == 'MultiPoint':
            return {"type": "MultiPoint", "coordinates": [list(p.coords[0]) for p in shape.geoms]}
        elif shape.geom_type == 'MultiLineString':
            return {"type": "MultiLineString", "coordinates": [list(line.coords) for line in shape.geoms]}
        else:
            return {"type": shape.geom_type, "coordinates": list(shape.coords)}
    except Exception as e:
        logger.error(f"Error converting geometry: {e}")
        return None

# -------------------------------
# Health Check Endpoint
# -------------------------------
@app.get("/health")
def health_check():
    """Health check endpoint for hosting platforms"""
    try:
        # Test database connection
        engine.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_status,
        "environment": ENVIRONMENT,
        "version": "1.0.0",
        "geocoding_available": geolocator is not None
    }

# -------------------------------
# Token endpoint
# -------------------------------
@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return {"access_token": access_token, "token_type": "bearer"}

# -------------------------------
# Plus Code Endpoints
# -------------------------------

@app.get("/api/geocode/address-to-pluscode")
def address_to_plus_code(address: str = Query(...)):
    """Convert address to plus code"""
    result = get_plus_code_from_address(address)
    return result

@app.get("/api/geocode/pluscode-to-address")
def plus_code_to_address(plus_code: str = Query(...)):
    """Convert plus code to address"""
    result = get_address_from_plus_code(plus_code)
    return result

@app.get("/api/geocode/coordinates-to-pluscode")
def coordinates_to_plus_code(lat: float = Query(...), lng: float = Query(...)):
    """Convert coordinates to plus code"""
    plus_code = get_plus_code_from_coordinates(lat, lng)
    return {
        "latitude": lat,
        "longitude": lng,
        "plus_code": plus_code
    }

@app.post("/api/features/batch-update-pluscodes")
def batch_update_plus_codes(current_user: dict = Depends(get_current_user)):
    """Batch update all plus codes for manholes and pipelines"""
    role = get_user_role(current_user.id)
    if role != 'engineer':
        raise HTTPException(status_code=403, detail="Only engineers can batch update plus codes")
    
    manhole_result = update_plus_codes_for_table('waste_water_manhole', 'gid')
    pipeline_result = update_plus_codes_for_table('waste_water_pipeline', 'gid')
    
    return {
        "manholes": manhole_result,
        "pipelines": pipeline_result
    }

@app.get("/api/features/search-by-pluscode")
def search_by_plus_code(
    plus_code: str = Query(...),
    radius_meters: float = Query(500),
    current_user: dict = Depends(get_current_user)
):
    """Search for features near a plus code location"""
    try:
        decoded = olc.decode(plus_code)
        lat = decoded.latitudeCenter
        lng = decoded.longitudeCenter
        
        # Search for manholes within radius
        manhole_query = f"""
            SELECT gid, manhole_id, bloc_stat, suburb_nam, plus_code,
                   ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography) as distance_meters
            FROM waste_water_manhole
            WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :radius)
            ORDER BY distance_meters
            LIMIT 20
        """
        
        manholes = pd.read_sql(manhole_query, engine, params={
            "lat": lat, "lng": lng, "radius": radius_meters
        })
        
        # Search for pipelines within radius
        pipeline_query = f"""
            SELECT gid, pipe_id, block_stat, plus_code,
                   ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography) as distance_meters
            FROM waste_water_pipeline
            WHERE ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :radius)
            ORDER BY distance_meters
            LIMIT 20
        """
        
        pipelines = pd.read_sql(pipeline_query, engine, params={
            "lat": lat, "lng": lng, "radius": radius_meters
        })
        
        return {
            "success": True,
            "search_location": {
                "plus_code": plus_code,
                "latitude": lat,
                "longitude": lng
            },
            "radius_meters": radius_meters,
            "manholes": manholes.to_dict(orient='records'),
            "pipelines": pipelines.to_dict(orient='records'),
            "total_found": len(manholes) + len(pipelines)
        }
    except Exception as e:
        logger.error(f"Search by plus code error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------
# Get All Manholes (with plus_code)
# -------------------------------
@app.get("/api/manholes")
def get_manholes(
    current_user: dict = Depends(get_current_user),
    status: Optional[str] = None,
    suburb: Optional[str] = None,
    flagged: Optional[bool] = None
):
    try:
        query = "SELECT * FROM waste_water_manhole WHERE 1=1"
        params = {}
        
        if status:
            query += " AND bloc_stat = :status"
            params["status"] = status
        if suburb:
            query += " AND suburb_nam = :suburb"
            params["suburb"] = suburb
        if flagged is not None:
            query += " AND flagged = :flagged"
            params["flagged"] = flagged
        
        query += " ORDER BY gid"
        
        df = pd.read_sql(query, engine, params=params)
        
        result = []
        for _, row in df.iterrows():
            item = row.to_dict()
            if 'geom' in item and item['geom']:
                item['geom'] = geom_to_geojson(item['geom'])
            
            # Generate plus code if not present
            if 'plus_code' not in item or not item['plus_code']:
                if row['geom']:
                    try:
                        shape = wkb.loads(row['geom'])
                        if shape.geom_type == 'Point':
                            lat = shape.y
                            lng = shape.x
                        else:
                            centroid = shape.centroid
                            lat = centroid.y
                            lng = centroid.x
                        item['plus_code'] = get_plus_code_from_coordinates(lat, lng)
                    except:
                        item['plus_code'] = None
            
            result.append(item)
        
        return result
    except Exception as e:
        logger.error(f"Error getting manholes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------
# Get All Pipelines (with plus_code)
# -------------------------------
@app.get("/api/pipelines")
def get_pipelines(
    current_user: dict = Depends(get_current_user),
    status: Optional[str] = None,
    material: Optional[str] = None,
    flagged: Optional[bool] = None
):
    try:
        query = "SELECT * FROM waste_water_pipeline WHERE 1=1"
        params = {}
        
        if status:
            query += " AND block_stat = :status"
            params["status"] = status
        if material:
            query += " AND pipe_mat = :material"
            params["material"] = material
        if flagged is not None:
            query += " AND flagged = :flagged"
            params["flagged"] = flagged
        
        query += " ORDER BY gid"
        
        df = pd.read_sql(query, engine, params=params)
        
        result = []
        for _, row in df.iterrows():
            item = row.to_dict()
            if 'geom' in item and item['geom']:
                item['geom'] = geom_to_geojson(item['geom'])
            
            # Generate plus code if not present
            if 'plus_code' not in item or not item['plus_code']:
                if row['geom']:
                    try:
                        shape = wkb.loads(row['geom'])
                        centroid = shape.centroid
                        item['plus_code'] = get_plus_code_from_coordinates(centroid.y, centroid.x)
                    except:
                        item['plus_code'] = None
            
            result.append(item)
        
        return result
    except Exception as e:
        logger.error(f"Error getting pipelines: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------
# Service Info
# -------------------------------
@app.get("/")
def root():
    return {
        "name": "Wastewater GIS Backend",
        "version": "1.0.0",
        "status": "running",
        "environment": ENVIRONMENT,
        "docs_url": "/api/docs",
        "health_check": "/health",
        "features": [
            "Plus Code Generation",
            "Address Geocoding",
            "Reverse Geocoding",
            "Spatial Search",
            "Manhole Management",
            "Pipeline Management"
        ],
        "endpoints": {
            "docs": "/api/docs",
            "health": "/health",
            "plus_codes": [
                "/api/geocode/address-to-pluscode",
                "/api/geocode/pluscode-to-address",
                "/api/geocode/coordinates-to-pluscode",
                "/api/features/batch-update-pluscodes",
                "/api/features/search-by-pluscode"
            ],
            "data": [
                "/api/manholes",
                "/api/pipelines"
            ]
        }
    }

@app.get("/api/info")
def service_info():
    return {
        "allowed_origins": ALLOWED_ORIGINS,
        "database_connected": True,
        "tables": inspect(engine).get_table_names() if engine else [],
        "plus_code_support": True,
        "environment": ENVIRONMENT,
        "geocoding_available": geolocator is not None
    }

# -------------------------------
# Error Handlers
# -------------------------------
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return {
        "error": exc.detail,
        "status_code": exc.status_code,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return {
        "error": "Internal server error",
        "status_code": 500,
        "timestamp": datetime.utcnow().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")