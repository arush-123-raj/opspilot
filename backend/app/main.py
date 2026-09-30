import json
from fastapi import FastAPI, Depends, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from jose import JWTError, jwt

from app import models, schemas, crud, security
from app.database import get_db
from app.redis_client import redis_db
from app.celery_worker import send_incident_alert

app = FastAPI(title="OpsPilot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
        email: str = payload.get("email")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = await crud.get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception
    return user

@app.get("/health")
async def health_check():
    try:
        await redis_db.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"disconnected: {str(e)}"
    return {"status": "healthy", "version": "0.1.0", "redis": redis_status}

@app.post("/login", response_model=schemas.Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = await crud.get_user_by_email(db, email=form_data.username)
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    access_token = security.create_access_token(data={"email": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/users/", response_model=schemas.UserResponse, status_code=201)
async def create_user(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    return await crud.create_user(db=db, user=user)

@app.post("/services/", response_model=schemas.ServiceResponse, status_code=201)
async def create_service(service: schemas.ServiceCreate, db: AsyncSession = Depends(get_db)):
    db_service = await crud.get_service_by_name(db, name=service.name)
    if db_service:
        raise HTTPException(status_code=400, detail="Service name already registered")
    return await crud.create_service(db=db, service=service)

@app.get("/services/", response_model=List[schemas.ServiceResponse])
async def read_services(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    return await crud.get_services(db, skip=skip, limit=limit)

@app.post("/incidents/", response_model=schemas.IncidentResponse, status_code=201)
async def create_incident(incident: schemas.IncidentCreate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_service = await crud.get_service(db, service_id=incident.service_id)
    if not db_service:
        raise HTTPException(status_code=404, detail="Linked Service not found")
        
    new_incident = await crud.create_incident(db=db, incident=incident)
    
    # Offload the alert to Celery if it is a high-severity incident
    if new_incident.severity in ["sev-1", "sev-2"]:
        send_incident_alert.delay(new_incident.title, new_incident.severity)
        
    return new_incident

@app.get("/incidents/", response_model=List[schemas.IncidentResponse])
async def read_incidents(response: Response, skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    cache_key = f"incidents_skip:{skip}_limit:{limit}"
    cached_data = await redis_db.get(cache_key)
    if cached_data:
        response.headers["X-Cache"] = "HIT"
        return json.loads(cached_data)
        
    response.headers["X-Cache"] = "MISS"
    incidents = await crud.get_incidents(db, skip=skip, limit=limit)
    incident_responses = [schemas.IncidentResponse.model_validate(i).model_dump(mode='json') for i in incidents]
    await redis_db.setex(cache_key, 30, json.dumps(incident_responses))
    return incidents

@app.patch("/incidents/{incident_id}", response_model=schemas.IncidentResponse)
async def update_incident(incident_id: int, incident_update: schemas.IncidentUpdate, db: AsyncSession = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db_incident = await crud.get_incident(db, incident_id=incident_id)
    if not db_incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    
    updated_incident = await crud.update_incident(db, db_incident=db_incident, incident_update=incident_update)
    
    # Invalidate the incident cache so the next GET request fetches fresh data
    await redis_db.flushdb()
    
    return updated_incident
