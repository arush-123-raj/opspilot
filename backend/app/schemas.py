from pydantic import BaseModel, ConfigDict, EmailStr
from datetime import datetime
from typing import Optional

# --- User Schemas ---
class UserBase(BaseModel):
    email: EmailStr
    name: str
    is_active: bool = True

class UserCreate(UserBase):
    pass

class UserResponse(UserBase):
    id: int
    created_at: datetime

    # Tells Pydantic to read data even if it is an ORM model instance
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
