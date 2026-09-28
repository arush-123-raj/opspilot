import json
from fastapi import FastAPI, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app import models, schemas, crud
from app.database import get_db
from app.redis_client import redis_db

app = FastAPI(title="OpsPilot API", version="0.1.0")

@app.get("/health")
async def health_check():
    try:
        await redis_db.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"disconnected: {str(e)}"
    return {"status": "healthy", "version": "0.1.0", "redis": redis_status}

# --- User Routes ---
@app.post("/users/", response_model=schemas.UserResponse, status_code=201)
async def create_user(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return await crud.create_user(db=db, user=user)

@app.get("/users/{user_id}", response_model=schemas.UserResponse)
async def read_user(user_id: int, db: AsyncSession = Depends(get_db)):
    db_user = await crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

# --- Service Routes ---
@app.post("/services/", response_model=schemas.ServiceResponse, status_code=201)
async def create_service(service: schemas.ServiceCreate, db: AsyncSession = Depends(get_db)):
    db_service = await crud.get_service_by_name(db, name=service.name)
    if db_service:
        raise HTTPException(status_code=400, detail="Service name already registered")
    return await crud.create_service(db=db, service=service)

@app.get("/services/", response_model=List[schemas.ServiceResponse])
async def read_services(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await crud.get_services(db, skip=skip, limit=limit)

# --- Incident Routes ---
@app.post("/incidents/", response_model=schemas.IncidentResponse, status_code=201)
async def create_incident(incident: schemas.IncidentCreate, db: AsyncSession = Depends(get_db)):
    db_service = await crud.get_service(db, service_id=incident.service_id)
    if not db_service:
        raise HTTPException(status_code=404, detail="Linked Service not found")
    return await crud.create_incident(db=db, incident=incident)

@app.get("/incidents/", response_model=List[schemas.IncidentResponse])
async def read_incidents(response: Response, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    cache_key = f"incidents_skip:{skip}_limit:{limit}"
    
    # 1. Check Redis Cache
    cached_data = await redis_db.get(cache_key)
    if cached_data:
        response.headers["X-Cache"] = "HIT"
        return json.loads(cached_data)
        
    # 2. If not cached, fetch from PostgreSQL
    response.headers["X-Cache"] = "MISS"
    incidents = await crud.get_incidents(db, skip=skip, limit=limit)
    
    # 3. Serialize and store in Redis for 30 seconds
    incident_responses = [schemas.IncidentResponse.model_validate(i).model_dump(mode='json') for i in incidents]
    await redis_db.setex(cache_key, 30, json.dumps(incident_responses))
    
    return incidents
