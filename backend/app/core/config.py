"""
Application configuration / environment.

Reads from environment variables with sane dev-friendly defaults.
Do NOT rely on the defaults in production — set real values in a .env or deploy env.
"""

import os
import secrets
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # --- JWT ---
    # Auto-generated fallback for dev; ALWAYS set SECRET_KEY in prod
    SECRET_KEY: str = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    # --- Cookies ---
    # Cookie name for the session/access token
    ACCESS_COOKIE_NAME: str = "fc_access"
    REFRESH_COOKIE_NAME: str = "fc_refresh"
    # In dev (HTTP) we cannot use Secure=True, browsers reject it. In prod, True.
    COOKIE_SECURE: bool = os.environ.get("COOKIE_SECURE", "false").lower() == "true"
    # SameSite: "lax" works for same-site + top-level navigations (incl OAuth redirect).
    # Use "none" only with Secure=True if frontend is on a different domain.
    COOKIE_SAMESITE: str = os.environ.get("COOKIE_SAMESITE", "lax")
    COOKIE_DOMAIN: str | None = os.environ.get("COOKIE_DOMAIN") or None

    # --- Frontend / CORS ---
    FRONTEND_URL: str = os.environ.get("FRONTEND_URL", "http://localhost:3000")
    # Comma-separated list of allowed origins
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.environ.get(
            "CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
        ).split(",")
        if o.strip()
    ]

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str | None = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: str | None = os.environ.get("GOOGLE_CLIENT_SECRET")
    # The backend OAuth callback URL registered with Google
    GOOGLE_REDIRECT_URI: str = os.environ.get(
        "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback"
    )

    @property
    def google_oauth_configured(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)


settings = Settings()
