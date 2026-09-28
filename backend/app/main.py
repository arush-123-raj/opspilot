from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app import models, schemas, crud
from app.database import get_db

app = FastAPI(title="OpsPilot API", version="0.1.0")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "0.1.0"}

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
    services = await crud.get_services(db, skip=skip, limit=limit)
    return services
