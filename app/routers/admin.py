from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import require_roles
from app.core.db import get_db
from app.core.security import hash_password
from app.models.user import User, UserRole

router = APIRouter(prefix="/admin", tags=["admin"])


# -------- Schemas --------
class AdminUserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=6, max_length=32)
    role: UserRole
    password: str = Field(min_length=8, max_length=128)
    is_active: bool = True


class AdminUserUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    phone: Optional[str] = Field(default=None, min_length=6, max_length=32)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class AdminPasswordReset(BaseModel):
    new_password: str = Field(min_length=8, max_length=128)


def _user_out(u: User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "phone": u.phone,
        "role": u.role.value,
        "is_active": bool(u.is_active),
        "created_at": u.created_at,
    }


# -------- Endpoints (ADMIN-only) --------
@router.get("/users")
def admin_list_users(
    role: Optional[UserRole] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    query = db.query(User)

    if role is not None:
        query = query.filter(User.role == role)

    if q:
        like = f"%{q.strip()}%"
        query = query.filter((User.name.ilike(like)) | (User.phone.ilike(like)))

    users = query.order_by(User.role.asc(), User.name.asc()).all()
    return [_user_out(u) for u in users]


@router.post("/users")
def admin_create_user(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    phone = payload.phone.strip()
    if not phone:
        raise HTTPException(status_code=400, detail="phone is required")

    existing = db.query(User).filter(User.phone == phone).first()
    if existing:
        raise HTTPException(status_code=409, detail="A user with this phone already exists")

    user = User(
        id=str(uuid.uuid4()),
        name=payload.name.strip(),
        phone=phone,
        role=payload.role,
        password_hash=hash_password(payload.password),
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.patch("/users/{user_id}")
def admin_update_user(
    user_id: str,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # safety: don't brick yourself
    if user.id == admin.id:
        if payload.role is not None and payload.role != UserRole.ADMIN:
            raise HTTPException(status_code=400, detail="You cannot change your own role")
        if payload.is_active is not None and payload.is_active is False:
            raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    if payload.phone is not None:
        new_phone = payload.phone.strip()
        if not new_phone:
            raise HTTPException(status_code=400, detail="phone cannot be blank")

        exists = db.query(User).filter(User.phone == new_phone, User.id != user.id).first()
        if exists:
            raise HTTPException(status_code=409, detail="Another user already has this phone")
        user.phone = new_phone

    if payload.name is not None:
        user.name = payload.name.strip()

    if payload.role is not None:
        user.role = payload.role

    if payload.is_active is not None:
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.post("/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: str,
    payload: AdminPasswordReset,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot reset your own password here")

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}
