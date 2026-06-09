import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.database import get_db
from app.models.parent import Parent
from app.models.child import Child
from app.models.gmail_connection import GmailConnection
from app.auth import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    create_oauth_state_token, decode_token, get_current_parent,
)
from app.services.crypto import encrypt_token
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

_GOOGLE_CLIENT_CONFIG = lambda: {  # noqa: E731
    "web": {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uris": [settings.google_redirect_uri],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, response: Response, db: Annotated[AsyncSession, Depends(get_db)]):
    existing = await db.execute(select(Parent).where(Parent.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    parent = Parent(email=body.email, password_hash=hash_password(body.password), full_name=body.full_name)
    db.add(parent)
    await db.commit()
    await db.refresh(parent)

    _set_refresh_cookie(response, create_refresh_token(parent.id))
    return {"access_token": create_access_token(parent.id, parent.email)}


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(Parent).where(Parent.email == body.email))
    parent = result.scalar_one_or_none()
    if not parent or not verify_password(body.password, parent.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    _set_refresh_cookie(response, create_refresh_token(parent.id))
    return {"access_token": create_access_token(parent.id, parent.email)}


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    try:
        payload = decode_token(token)
        if payload.get("type") != "refresh":
            raise ValueError
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await db.execute(select(Parent).where(Parent.id == uuid.UUID(payload["sub"])))
    parent = result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=401, detail="Parent not found")

    return {"access_token": create_access_token(parent.id, parent.email)}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("refresh_token")
    return {"detail": "Logged out"}


@router.get("/google/connect")
async def google_connect(
    child_id: str,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(Child).where(Child.id == uuid.UUID(child_id), Child.parent_id == current_parent.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")

    flow = Flow.from_client_config(_GOOGLE_CLIENT_CONFIG(), scopes=GMAIL_SCOPES, redirect_uri=settings.google_redirect_uri)
    state = create_oauth_state_token(current_parent.id, uuid.UUID(child_id))
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state)
    return RedirectResponse(auth_url)


@router.get("/google/callback")
async def google_callback(code: str, state: str, db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        payload = decode_token(state)
        if payload.get("type") != "oauth_state":
            raise ValueError
        parent_id = uuid.UUID(payload["parent_id"])
        child_id = uuid.UUID(payload["child_id"])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    flow = Flow.from_client_config(
        _GOOGLE_CLIENT_CONFIG(), scopes=GMAIL_SCOPES,
        redirect_uri=settings.google_redirect_uri, state=state,
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    userinfo_service = build("oauth2", "v2", credentials=creds)
    gmail_address = userinfo_service.userinfo().get().execute()["email"]

    existing = await db.execute(
        select(GmailConnection).where(
            GmailConnection.child_id == child_id,
            GmailConnection.gmail_address == gmail_address,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Gmail account already connected")

    conn = GmailConnection(
        child_id=child_id,
        gmail_address=gmail_address,
        access_token=encrypt_token(creds.token),
        refresh_token=encrypt_token(creds.refresh_token),
        token_expiry=creds.expiry or (datetime.now(timezone.utc) + timedelta(hours=1)),
    )
    db.add(conn)
    await db.commit()

    return RedirectResponse(f"{settings.frontend_url}/dashboard?connected=true")


@router.delete("/google/{connection_id}", status_code=204)
async def disconnect_gmail(
    connection_id: str,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        select(GmailConnection)
        .join(Child, Child.id == GmailConnection.child_id)
        .where(GmailConnection.id == uuid.UUID(connection_id), Child.parent_id == current_parent.id)
    )
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    await db.delete(conn)
    await db.commit()


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "refresh_token", token,
        httponly=True, secure=True, samesite="strict",
        max_age=60 * 60 * 24 * 30,
    )
