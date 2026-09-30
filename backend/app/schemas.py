from pydantic import BaseModel, ConfigDict, EmailStr
from datetime import datetime
from typing import Optional, List

# --- Token Schemas ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr
    name: str
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- Service Schemas ---
class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None
    repository_url: Optional[str] = None

class ServiceCreate(ServiceBase):
    pass

class ServiceResponse(ServiceBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- AuditLog Schemas ---
class AuditLogResponse(BaseModel):
    id: int
    incident_id: int
    action: str
    details: Optional[str] = None
    timestamp: datetime
    model_config = ConfigDict(from_attributes=True)

# --- Incident Schemas ---
class IncidentBase(BaseModel):
    title: str
    description: str
    status: str = "investigating"
    severity: str = "sev-3"
    service_id: int

class IncidentCreate(IncidentBase):
    pass

class IncidentResponse(IncidentBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    severity: Optional[str] = None
