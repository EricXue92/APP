from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "type": "access", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": user_id, "type": "refresh", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        return None


def generate_ntrp_label(level: str) -> str:
    labels = {
        "1.0": "1.0 初学者", "1.5": "1.5 初学者",
        "2.0": "2.0 初级", "2.5": "2.5 初级",
        "3.0": "3.0 中初级", "3.5": "3.5 中级",
        "4.0": "4.0 中高级", "4.5": "4.5 高级",
        "5.0": "5.0 高级", "5.5": "5.5 准专业",
        "6.0": "6.0 专业", "6.5": "6.5 专业", "7.0": "7.0 世界级",
    }
    base = level.rstrip("+-")
    label = labels.get(base, f"{base}")
    if level.endswith("+"):
        return f"{label}+"
    elif level.endswith("-"):
        return f"{label}-"
    return label
