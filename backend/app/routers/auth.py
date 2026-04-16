"""
Auth Router
===========
Email/password signup + login, logout, refresh, current-user, Google OAuth.

All auth state is carried in httpOnly cookies:
  - fc_access  (path=/)         short-lived JWT for API calls
  - fc_refresh (path=/api/auth)  long-lived JWT to mint new access tokens
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.core.config import settings
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.db import get_db
from app.db.models import User


router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: str | None = None
    avatar_url: str | None = None
    has_password: bool
    has_google: bool

    @classmethod
    def from_model(cls, u: User) -> "UserOut":
        return cls(
            id=u.id,
            email=u.email,
            name=u.name,
            avatar_url=u.avatar_url,
            has_password=bool(u.password_hash),
            has_google=bool(u.google_id),
        )


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Email + password
# ---------------------------------------------------------------------------
@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def signup(
    req: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    email = req.email.lower().strip()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=email,
        password_hash=hash_password(req.password),
        name=(req.name or "").strip() or None,
    )
    db.add(user)
    await db.flush()  # get user.id

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    set_auth_cookies(response, access, refresh)

    await db.commit()
    await db.refresh(user)
    return UserOut.from_model(user)


@router.post("/login", response_model=UserOut)
async def login(
    req: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    email = req.email.lower().strip()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Constant-ish-time behavior: still run verify on a dummy hash if no user
    if not user or not user.password_hash or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled.",
        )

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    set_auth_cookies(response, access, refresh)

    return UserOut.from_model(user)


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    clear_auth_cookies(response)
    return MessageResponse(message="Logged out")


@router.post("/refresh", response_model=MessageResponse)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    payload = decode_refresh_token(token)
    if not payload:
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        clear_auth_cookies(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)  # rotate refresh token
    set_auth_cookies(response, access, refresh)
    return MessageResponse(message="Refreshed")


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return UserOut.from_model(current_user)


# ---------------------------------------------------------------------------
# Google OAuth (manual, no extra dependency surface)
# ---------------------------------------------------------------------------
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# state cookie (short-lived, CSRF protection for OAuth)
_STATE_COOKIE = "fc_oauth_state"


@router.get("/google/start")
async def google_start(request: Request):
    """Kick off the Google OAuth flow — redirects to Google."""
    if not settings.google_oauth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured on the server.",
        )

    state = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    }
    url = f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"

    resp = RedirectResponse(url=url, status_code=302)
    resp.set_cookie(
        key=_STATE_COOKIE,
        value=state,
        max_age=600,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/api/auth",
    )
    return resp


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google's redirect back — exchange code, upsert user, set cookies, bounce to frontend."""
    frontend_login = f"{settings.FRONTEND_URL.rstrip('/')}/login"

    if error:
        return RedirectResponse(f"{frontend_login}?error={error}", status_code=302)
    if not code or not state:
        return RedirectResponse(f"{frontend_login}?error=missing_code", status_code=302)

    expected_state = request.cookies.get(_STATE_COOKIE)
    if not expected_state or not secrets.compare_digest(expected_state, state):
        return RedirectResponse(f"{frontend_login}?error=invalid_state", status_code=302)

    if not settings.google_oauth_configured:
        return RedirectResponse(f"{frontend_login}?error=oauth_not_configured", status_code=302)

    # 1. Exchange code for tokens
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            if token_resp.status_code != 200:
                return RedirectResponse(f"{frontend_login}?error=token_exchange_failed", status_code=302)
            tokens = token_resp.json()
            access_token = tokens.get("access_token")
            if not access_token:
                return RedirectResponse(f"{frontend_login}?error=no_access_token", status_code=302)

            # 2. Fetch user info
            ui_resp = await client.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if ui_resp.status_code != 200:
                return RedirectResponse(f"{frontend_login}?error=userinfo_failed", status_code=302)
            info = ui_resp.json()
    except httpx.HTTPError:
        return RedirectResponse(f"{frontend_login}?error=google_unreachable", status_code=302)

    google_sub = info.get("sub")
    email = (info.get("email") or "").lower().strip()
    email_verified = bool(info.get("email_verified"))
    name = info.get("name")
    picture = info.get("picture")

    if not google_sub or not email:
        return RedirectResponse(f"{frontend_login}?error=invalid_profile", status_code=302)
    if not email_verified:
        return RedirectResponse(f"{frontend_login}?error=email_not_verified", status_code=302)

    # 3. Upsert user — match on google_id first, then email
    result = await db.execute(select(User).where(User.google_id == google_sub))
    user = result.scalar_one_or_none()

    if not user:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            # Existing email/password account — link Google
            user.google_id = google_sub
            if not user.avatar_url and picture:
                user.avatar_url = picture
            if not user.name and name:
                user.name = name
        else:
            user = User(
                email=email,
                google_id=google_sub,
                name=name,
                avatar_url=picture,
                password_hash=None,
            )
            db.add(user)

    await db.flush()

    # 4. Set cookies + redirect to frontend
    redirect = RedirectResponse(url=settings.FRONTEND_URL, status_code=302)
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    set_auth_cookies(redirect, access, refresh)
    # clear the oauth state cookie
    redirect.delete_cookie(_STATE_COOKIE, path="/api/auth")
    await db.commit()
    return redirect


@router.get("/providers")
async def auth_providers():
    """Report which auth providers are available (e.g. hide Google button if not configured)."""
    return {
        "password": True,
        "google": settings.google_oauth_configured,
    }
