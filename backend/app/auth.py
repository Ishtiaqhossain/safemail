import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.database import get_db

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()

_private_key: str | None = None
_public_key: str | None = None


def _load_keys() -> None:
    global _private_key, _public_key
    if _private_key is None:
        _private_key = Path(settings.jwt_private_key_path).read_text()
    if _public_key is None:
        _public_key = Path(settings.jwt_public_key_path).read_text()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(parent_id: uuid.UUID, email: str, is_admin: bool = False, is_developer: bool = False) -> str:
    _load_keys()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": str(parent_id), "email": email, "is_admin": is_admin, "is_developer": is_developer, "exp": expire, "type": "access"},
        _private_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(parent_id: uuid.UUID) -> str:
    _load_keys()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    return jwt.encode(
        {"sub": str(parent_id), "exp": expire, "type": "refresh"},
        _private_key,
        algorithm=settings.jwt_algorithm,
    )


def create_oauth_state_token(parent_id: uuid.UUID, child_id: uuid.UUID) -> str:
    _load_keys()
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    return jwt.encode(
        {"parent_id": str(parent_id), "child_id": str(child_id), "exp": expire, "type": "oauth_state"},
        _private_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict:
    _load_keys()
    return jwt.decode(token, _public_key, algorithms=[settings.jwt_algorithm])


async def get_current_parent(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    from app.models.parent import Parent

    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise exc
        parent_id = payload.get("sub")
        if not parent_id:
            raise exc
    except JWTError:
        raise exc

    result = await db.execute(select(Parent).where(Parent.id == uuid.UUID(parent_id)))
    parent = result.scalar_one_or_none()
    if parent is None:
        raise exc
    return parent


async def get_current_admin(
    parent: Annotated["Parent", Depends(get_current_parent)],
) -> "Parent":
    if not parent.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return parent


async def get_current_developer(
    parent: Annotated["Parent", Depends(get_current_parent)],
) -> "Parent":
    if not parent.is_developer:
        raise HTTPException(status_code=403, detail="Developer access required")
    return parent
