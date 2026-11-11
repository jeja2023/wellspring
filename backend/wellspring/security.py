from datetime import datetime, timezone
import hashlib, hmac, os, secrets
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session as DBSession
from .db import get_db
from .models import Session, User, Organization
from .credentials import NEW_PASSWORD_MIN_LENGTH, ORGANIZATION_MAX_LENGTH, PASSWORD_MAX_LENGTH, USERNAME_MAX_LENGTH

# A fixed non-account hash makes unknown-user checks perform the same expensive
# operation. It cannot be used to authenticate any stored account.
DUMMY_PASSWORD_HASH = "pbkdf2_sha256$600000$00000000000000000000000000000000$" + "0" * 64

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

def current_user(request: Request, authorization: str | None = Header(default=None), db: DBSession = Depends(get_db)) -> User:
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
    organization=db.get(Organization,user.org_id)
    if not organization or not organization.active:
        raise auth_error(401,"UNAUTHENTICATED","所属组织已停用，会话失效")
    from .access_policy import effective_permissions,route_permissions
    permissions=effective_permissions(db,user)
    user._effective_permissions=permissions
    if not user.is_admin and not route_permissions(request.method,request.url.path) <= permissions:
        raise auth_error(403,"FORBIDDEN","当前角色无此操作权限")
    user._authenticated_session=session.token_hash
    return user


def current_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise auth_error(403, "FORBIDDEN", "需要管理员权限")
    return user
