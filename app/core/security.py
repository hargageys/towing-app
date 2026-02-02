from datetime import datetime, timedelta

from jose import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

ph = PasswordHasher()  # Argon2id by default


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(subject: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])

# from datetime import datetime, timedelta
# from typing import Optional

# from jose import jwt
# from passlib.context import CryptContext

# from app.core.config import settings

# pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# def hash_password(password: str) -> str:
#     return pwd_context.hash(password)


# def verify_password(password: str, password_hash: str) -> bool:
#     return pwd_context.verify(password, password_hash)


# def create_access_token(subject: str, role: str) -> str:
#     expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
#     payload = {"sub": subject, "role": role, "exp": expire}
#     return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


# def decode_token(token: str) -> dict:
#     return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
