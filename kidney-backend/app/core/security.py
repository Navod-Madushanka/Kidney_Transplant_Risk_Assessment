# app/core/security.py
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.core.config import get_settings


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(data: dict) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = data.copy()
    payload["exp"] = expire

    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
