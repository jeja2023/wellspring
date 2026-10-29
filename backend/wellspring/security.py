from datetime import datetime, timezone
import hashlib, hmac, os, secrets
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session as DBSession
from .db import get_db
from .models import Session, User

def password_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)
    return f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"

def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def new_token() -> str:
    return secrets.token_urlsafe(32)

def auth_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message, "details": []})

def current_user(authorization: str | None = Header(default=None), db: DBSession = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise auth_error(401, "UNAUTHENTICATED", "请先登录")
    raw_token = authorization[7:].strip()
    if not raw_token:
        raise auth_error(401, "UNAUTHENTICATED", "会话无效")
    session = db.get(Session, token_hash(raw_token))
    if not session:
        raise auth_error(401, "UNAUTHENTICATED", "会话无效")
    expires = session.expires_at.replace(tzinfo=timezone.utc) if session.expires_at.tzinfo is None else session.expires_at
    user = db.get(User, session.user_id)
    if expires <= datetime.now(timezone.utc) or not user or not user.active:
        raise auth_error(401, "UNAUTHENTICATED", "会话已失效")
    return user
