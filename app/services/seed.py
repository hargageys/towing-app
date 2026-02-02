import uuid
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User, UserRole


def seed_users(db: Session):
    # Only seed if no users exist
    if db.query(User).count() > 0:
        return

    users = [
        User(
            id=str(uuid.uuid4()),
            name="Officer One",
            phone="+252634000001",
            role=UserRole.OFFICER,
            password_hash=hash_password("officer123"),
            is_active=True,
        ),
        User(
            id=str(uuid.uuid4()),
            name="Driver One",
            phone="+252634000002",
            role=UserRole.DRIVER,
            password_hash=hash_password("driver123"),
            is_active=True,
        ),
        User(
            id=str(uuid.uuid4()),
            name="Dispatcher One",
            phone="+252634000003",
            role=UserRole.DISPATCHER,
            password_hash=hash_password("dispatch123"),
            is_active=True,
        ),
        User(
            id=str(uuid.uuid4()),
            name="Admin",
            phone="+252634000004",
            role=UserRole.ADMIN,
            password_hash=hash_password("admin123"),
            is_active=True,
        ),
    ]

    db.add_all(users)
    db.commit()
