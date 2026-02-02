from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.auth import require_roles
from app.models.user import User, UserRole

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def list_users(
    role: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.DISPATCHER, UserRole.ADMIN)),
):
    q = db.query(User)
    if role:
        try:
            q = q.filter(User.role == UserRole(role))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid role")
    users = q.all()
    return [
        {"id": u.id, "name": u.name, "phone": u.phone, "role": u.role.value, "is_active": u.is_active}
        for u in users
    ]

