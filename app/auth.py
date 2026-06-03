from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bcrypt
from itsdangerous import URLSafeTimedSerializer
from jose import JWTError, jwt

from .config import settings

_serializer = URLSafeTimedSerializer(settings.secret_key)

TOKEN_EXPIRE_DAYS = 7
VERIFY_TOKEN_MAX_AGE = 86400  # 24 h


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        settings.secret_key,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None


def generate_verification_token(email: str) -> str:
    return _serializer.dumps(email, salt="email-verify")


def verify_email_token(token: str) -> str | None:
    try:
        return _serializer.loads(token, salt="email-verify", max_age=VERIFY_TOKEN_MAX_AGE)
    except Exception:
        return None
