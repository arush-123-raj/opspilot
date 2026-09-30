from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app import models, schemas
from app.security import get_password_hash
from app.aiops_engine import triage_error_log

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
    # Run Phase 4 AI Log Triage automatically on new incident descriptions
    triage = triage_error_log(f"{incident.title} {incident.description}")
    enriched_desc = f"[{triage['tag']}] {incident.description} | AI Summary: {triage['summary']}"

    db_incident = models.Incident(
        title=incident.title,
        description=enriched_desc,
        status=incident.status,
        severity=incident.severity,
        service_id=incident.service_id,
    )
    db.add(db_incident)
    await db.flush()

    audit = models.AuditLog(
        incident_id=db_incident.id,
        action="CREATED_AND_AI_TRIAGED",
        details=f"Classified as [{triage['tag']}]: {triage['summary']}"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(db_incident)
    return db_incident

async def get_incidents(db: AsyncSession, skip: int = 0, limit: int = 100):
    result = await db.execute(
        select(models.Incident).order_by(models.Incident.id.desc()).offset(skip).limit(limit)
    )
    return result.scalars().all()

async def get_incident(db: AsyncSession, incident_id: int):
    result = await db.execute(select(models.Incident).where(models.Incident.id == incident_id))
    return result.scalars().first()

async def update_incident(db: AsyncSession, db_incident: models.Incident, incident_update: schemas.IncidentUpdate):
    update_data = incident_update.model_dump(exclude_unset=True)
    changes = []
    for key, value in update_data.items():
        old_val = getattr(db_incident, key)
        if old_val != value:
            changes.append(f"{key}: '{old_val}' -> '{value}'")
        setattr(db_incident, key, value)

    db.add(db_incident)
    if changes:
        audit = models.AuditLog(
            incident_id=db_incident.id,
            action="INCIDENT_UPDATED",
            details="; ".join(changes)
        )
        db.add(audit)

    await db.commit()
    await db.refresh(db_incident)
    return db_incident

async def get_incident_audit_logs(db: AsyncSession, incident_id: int):
    result = await db.execute(
        select(models.AuditLog)
        .where(models.AuditLog.incident_id == incident_id)
        .order_by(models.AuditLog.timestamp.asc())
    )
    return result.scalars().all()
