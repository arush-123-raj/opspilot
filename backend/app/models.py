from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String)
    repository_url = Column(String)  # Also used by Celery Active Poller as target URL
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    incidents = relationship("Incident", back_populates="service", cascade="all, delete-orphan")

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False)
    description = Column(String, nullable=False)
    status = Column(String, default="investigating")  # investigating, identified, monitoring, resolved
    severity = Column(String, default="sev-3")        # sev-1, sev-2, sev-3
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    service = relationship("Service", back_populates="incidents")
    audit_logs = relationship("AuditLog", back_populates="incident", cascade="all, delete-orphan")

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"), nullable=False)
    action = Column(String, nullable=False)  # CREATED, DEDUPLICATED_HEARTBEAT, AUTO_RESOLVED, etc.
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    incident = relationship("Incident", back_populates="audit_logs")
