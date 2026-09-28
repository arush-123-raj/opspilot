from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models, schemas

# --- User CRUD ---

async def get_user(db: AsyncSession, user_id: int):
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    return result.scalars().first()

async def get_user_by_email(db: AsyncSession, email: str):
    result = await db.execute(select(models.User).where(models.User.email == email))
    return result.scalars().first()

async def create_user(db: AsyncSession, user: schemas.UserCreate):
    # Convert the Pydantic schema into a SQLAlchemy model dictionary using model_dump()
    db_user = models.User(**user.model_dump())
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

# --- Service CRUD ---

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
