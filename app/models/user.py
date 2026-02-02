import enum
from sqlalchemy import Column, String, Boolean, DateTime, Enum
from sqlalchemy.sql import func

from app.core.db import Base


class UserRole(str, enum.Enum):
    OFFICER = "OFFICER"
    DRIVER = "DRIVER"
    DISPATCHER = "DISPATCHER"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)  # uuid string
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=False)
    role = Column(Enum(UserRole), nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
