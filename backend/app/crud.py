from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models, schemas
from app.security import get_password_hash

async def get_user(db: AsyncSession, user_id: int):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    return result.scalars().first()

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(models.User).where(models.User.email == email))
    return result.scalars().first()

async def create_user(db: AsyncSession, user: schemas.UserCreate):
    hashed_password = get_password_hash(user.password)
    user_data = user.model_dump()
    user_data.pop("password")
    user_data["hashed_password"] = hashed_password
    
    db_user = models.User(**user_data)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

async def get_service(db: AsyncSession, service_id: int):
    result = await db.execute(select(models.Service).where(models.Service.id == service_id))
    return result.scalars().first()

async def get_service_by_name(db: AsyncSession, name: str):
    result = await db.execute(select(models.Service).where(models.Service.name == name))
    return result.scalars().first()

async def get_services(db: AsyncSession, skip: int = 0, limit: int = 100):
    result = await db.execute(select(models.Service).offset(skip).limit(limit))
    return result.scalars().all()

async def create_service(db: AsyncSession, service: schemas.ServiceCreate):
    db_service = models.Service(**service.model_dump())
    db.add(db_service)
    await db.commit()
    await db.refresh(db_service)
    return db_service

async def create_incident(db: AsyncSession, incident: schemas.IncidentCreate):
    db_incident = models.Incident(**incident.model_dump())
    db.add(db_incident)
    await db.commit()
    await db.refresh(db_incident)
    return db_incident

async def get_incidents(db: AsyncSession, skip: int = 0, limit: int = 100):
    result = await db.execute(select(models.Incident).offset(skip).limit(limit))
    return result.scalars().all()

async def get_incident(db: AsyncSession, incident_id: int):
    result = await db.execute(select(models.Incident).where(models.Incident.id == incident_id))
    return result.scalars().first()

async def update_incident(db: AsyncSession, db_incident: models.Incident, incident_update: schemas.IncidentUpdate):
    update_data = incident_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_incident, key, value)
    db.add(db_incident)
    await db.commit()
    await db.refresh(db_incident)
    return db_incident
