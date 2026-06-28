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
    create_oauth_state_token, create_password_reset_token,
    create_email_verification_token,
    decode_token, get_current_parent,
)
from app.services.crypto import encrypt_token, decrypt_token
from app.services.gmail import revoke_token
from app.services import token_denylist
from app.services.analytics_events import record_event_async
from app.models.allowed_email import AllowedEmail
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, ForgotPasswordRequest, ResetPasswordRequest
from app.ratelimit import (
    limiter, LOGIN_LIMIT, REGISTER_LIMIT, REFRESH_LIMIT,
    FORGOT_PASSWORD_LIMIT, RESET_PASSWORD_LIMIT, RESEND_VERIFICATION_LIMIT,
)
from app.services.allowlist import is_email_allowed, parent_count

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
@limiter.limit(REGISTER_LIMIT)
async def register(request: Request, body: RegisterRequest, response: Response, db: Annotated[AsyncSession, Depends(get_db)]):
    existing = await db.execute(select(Parent).where(Parent.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Invite-only gate. The very first account (empty parents table) is always
    # allowed so a fresh deploy can bootstrap its admin without a chicken-and-egg.
    if settings.invite_only_enabled:
        if await parent_count(db) > 0 and not await is_email_allowed(db, body.email):
            raise HTTPException(
                status_code=403,
                detail="SafeMail is in invite-only alpha — your email isn't on the list yet.",
            )

    parent = Parent(email=body.email, password_hash=hash_password(body.password), full_name=body.full_name)
    db.add(parent)
    await db.commit()
    await db.refresh(parent)
    await record_event_async(db, "account_registered", parent_id=parent.id)

    # Send verification email (best-effort — don't fail registration if email is down)
    try:
        from app.services.notifications import send_verification_email
        token = create_email_verification_token(parent.id, parent.email)
        verify_url = f"{settings.frontend_url}/verify-email?token={token}"
        send_verification_email(parent.email, verify_url)
    except Exception:
        pass

    _set_refresh_cookie(response, create_refresh_token(parent.id))
    return {
        "access_token": create_access_token(parent.id, parent.email, parent.is_admin, parent.is_developer, parent.is_email_verified),
        "is_admin": parent.is_admin,
        "is_developer": parent.is_developer,
        "is_email_verified": parent.is_email_verified,
        "onboarding_completed": parent.onboarding_completed_at is not None,
        "monitoring_consent": parent.monitoring_consent_at is not None,
    }


@router.post("/login", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)
async def login(request: Request, body: LoginRequest, response: Response, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(Parent).where(Parent.email == body.email))
    parent = result.scalar_one_or_none()
    if not parent or not verify_password(body.password, parent.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Invite-only gate. Admins are exempt so the operator can't lock themselves out;
    # everyone else must remain on the allowlist (supports revoking access).
    if settings.invite_only_enabled and not parent.is_admin and not await is_email_allowed(db, body.email):
        raise HTTPException(
            status_code=403,
            detail="Your access to the SafeMail alpha isn't enabled.",
        )

    await record_event_async(db, "login_succeeded", parent_id=parent.id)
    _set_refresh_cookie(response, create_refresh_token(parent.id))
    return {
        "access_token": create_access_token(parent.id, parent.email, parent.is_admin, parent.is_developer, parent.is_email_verified),
        "is_admin": parent.is_admin,
        "is_developer": parent.is_developer,
        "is_email_verified": parent.is_email_verified,
        "onboarding_completed": parent.onboarding_completed_at is not None,
        "monitoring_consent": parent.monitoring_consent_at is not None,
    }


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit(REFRESH_LIMIT)
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

    if await token_denylist.is_revoked(payload.get("jti")):
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    result = await db.execute(select(Parent).where(Parent.id == uuid.UUID(payload["sub"])))
    parent = result.scalar_one_or_none()
    if not parent:
        raise HTTPException(status_code=401, detail="Parent not found")

    return {
        "access_token": create_access_token(parent.id, parent.email, parent.is_admin, parent.is_developer, parent.is_email_verified),
        "is_admin": parent.is_admin,
        "is_developer": parent.is_developer,
        "is_email_verified": parent.is_email_verified,
        "onboarding_completed": parent.onboarding_completed_at is not None,
        "monitoring_consent": parent.monitoring_consent_at is not None,
    }


@router.post("/logout")
async def logout(request: Request, response: Response):
    # Revoke the refresh token server-side so it can't mint new access tokens
    # after logout, then clear the cookie. Best-effort: a malformed/expired
    # token has nothing to revoke.
    token = request.cookies.get("refresh_token")
    if token:
        try:
            payload = decode_token(token)
            ttl = int(payload["exp"] - datetime.now(timezone.utc).timestamp())
            await token_denylist.revoke(payload.get("jti"), ttl)
        except Exception:
            pass
    response.delete_cookie("refresh_token")
    return {"detail": "Logged out"}


@router.get("/verify-email")
async def verify_email(token: str, db: Annotated[AsyncSession, Depends(get_db)]):
    invalid = HTTPException(status_code=400, detail="Verification link is invalid or has expired.")
    try:
        payload = decode_token(token)
        if payload.get("type") != "email_verification":
            raise invalid
        parent_id = payload.get("sub")
    except Exception:
        raise invalid

    result = await db.execute(select(Parent).where(Parent.id == uuid.UUID(parent_id)))
    parent = result.scalar_one_or_none()
    if not parent:
        raise invalid

    parent.is_email_verified = True
    await db.commit()
    await record_event_async(db, "email_verified", parent_id=parent.id)
    return RedirectResponse(f"{settings.frontend_url}/dashboard?verified=true")


@router.post("/resend-verification", status_code=200)
@limiter.limit(RESEND_VERIFICATION_LIMIT)
async def resend_verification(
    request: Request,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
):
    if current_parent.is_email_verified:
        return {"detail": "Email already verified."}
    try:
        from app.services.notifications import send_verification_email
        token = create_email_verification_token(current_parent.id, current_parent.email)
        verify_url = f"{settings.frontend_url}/verify-email?token={token}"
        send_verification_email(current_parent.email, verify_url)
    except Exception:
        pass
    return {"detail": "Verification email sent."}


@router.post("/forgot-password", status_code=200)
@limiter.limit(FORGOT_PASSWORD_LIMIT)
async def forgot_password(request: Request, body: ForgotPasswordRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(select(Parent).where(Parent.email == body.email))
    parent = result.scalar_one_or_none()
    if parent:
        from app.services.notifications import send_password_reset_email
        token = create_password_reset_token(parent.id, parent.email)
        reset_url = f"{settings.frontend_url}/reset-password?token={token}"
        try:
            send_password_reset_email(parent.email, reset_url)
        except Exception:
            pass  # never reveal send failures to caller
    return {"detail": "If an account with that email exists, a reset link has been sent."}


@router.post("/reset-password", status_code=200)
@limiter.limit(RESET_PASSWORD_LIMIT)
async def reset_password(request: Request, body: ResetPasswordRequest, db: Annotated[AsyncSession, Depends(get_db)]):
    invalid = HTTPException(status_code=400, detail="Reset link is invalid or has expired.")
    try:
        payload = decode_token(body.token)
        if payload.get("type") != "password_reset":
            raise invalid
        parent_id = payload.get("sub")
    except Exception:
        raise invalid

    result = await db.execute(select(Parent).where(Parent.id == uuid.UUID(parent_id)))
    parent = result.scalar_one_or_none()
    if not parent:
        raise invalid

    parent.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"detail": "Password updated. You can now log in."}


@router.get("/google/connect")
async def google_connect(
    child_id: str,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
    return_to: str | None = None,
):
    result = await db.execute(
        select(Child).where(Child.id == uuid.UUID(child_id), Child.parent_id == current_parent.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Child not found")

    flow = Flow.from_client_config(_GOOGLE_CLIENT_CONFIG(), scopes=GMAIL_SCOPES, redirect_uri=settings.google_redirect_uri)
    state = create_oauth_state_token(current_parent.id, uuid.UUID(child_id), return_to=return_to)
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state)
    return {"auth_url": auth_url}


def _safe_return_path(return_to: str | None) -> str:
    """Only allow same-app relative paths to avoid open-redirects."""
    if return_to and return_to.startswith("/") and not return_to.startswith("//"):
        return return_to
    return "/dashboard?connected=true"


@router.get("/google/callback")
async def google_callback(code: str, state: str, db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        payload = decode_token(state)
        if payload.get("type") != "oauth_state":
            raise ValueError
        parent_id = uuid.UUID(payload["parent_id"])
        child_id = uuid.UUID(payload["child_id"])
        return_to = payload.get("return_to")
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
    await record_event_async(db, "gmail_connected", parent_id=parent_id)

    return RedirectResponse(f"{settings.frontend_url}{_safe_return_path(return_to)}")


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
    await record_event_async(db, "gmail_disconnected", parent_id=current_parent.id)


@router.delete("/account", status_code=204)
async def delete_account(
    response: Response,
    current_parent: Annotated[Parent, Depends(get_current_parent)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Permanently erase a parent and all associated data.

    Order matters: revoke Google OAuth grants first (while tokens still exist in
    the DB), then delete the parent. The parents -> children -> {connections,
    alerts, preferences, weekly_stats} FK cascade wipes every child record.
    Finally drop the parent's invite-allowlist entry so their email is fully
    erased. No raw email bodies are stored, so nothing else persists.
    """
    from sqlalchemy import func, delete as sa_delete

    # Churn signal recorded anonymously (parent_id=None) so it survives the
    # cascade delete below and stays countable after the account is gone.
    await record_event_async(db, "account_deleted")

    # 1. Revoke every Gmail grant at Google so we stop holding access after
    #    deletion. Best-effort — a failed revoke must not block local erasure.
    conns = await db.execute(
        select(GmailConnection)
        .join(Child, Child.id == GmailConnection.child_id)
        .where(Child.parent_id == current_parent.id)
    )
    for conn in conns.scalars().all():
        try:
            revoke_token(decrypt_token(conn.refresh_token))
        except Exception:
            pass

    # 2. Drop the invite-allowlist row matching this parent's email
    #    (case-insensitive, mirroring how the allowlist is checked elsewhere).
    await db.execute(
        sa_delete(AllowedEmail).where(func.lower(AllowedEmail.email) == current_parent.email.strip().lower())
    )

    # 3. Delete the parent. A Core DELETE lets Postgres' ON DELETE CASCADE wipe
    #    children -> {connections, alerts, preferences, weekly_stats} in one shot;
    #    we avoid ORM relationship cascade here because lazy-loading the relations
    #    isn't possible under the async session.
    await db.execute(sa_delete(Parent).where(Parent.id == current_parent.id))
    await db.commit()

    # 4. Invalidate the session.
    response.delete_cookie("refresh_token")


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "refresh_token", token,
        httponly=True, secure=settings.cookie_secure, samesite="strict",
        max_age=60 * 60 * 24 * 30,
    )
