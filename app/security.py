"""Password hashing, access tokens, and the current-user dependency.

This replaced a single shared `X-API-Key`. The shared key could not express "whose
data is this", which is the whole point of having accounts, so it is gone rather than
kept alongside — two authentication paths into the same rows is twice the surface to
get wrong, and the one caller that used to need a key (the daily scheduler) can log in
like anything else.

Decisions worth defending:

  * **Argon2id, not bcrypt.** Both are fine; Argon2id is memory-hard, so an attacker
    with GPUs gains much less over a defender with a CPU. bcrypt's 72-byte input limit
    is also a sharp edge Argon2 does not have. `PasswordHash.recommended()` tracks the
    current best choice so this file does not have to.

  * **The hash is verified even when the email is unknown.** Returning early on a
    missing account makes login measurably faster for non-existent emails, which turns
    the endpoint into an account-enumeration oracle. The dummy verify keeps both paths
    on the same order of magnitude.

  * **Login failures do not say which half was wrong.** "No such user" is the same
    information leak spelled out in words.

  * **`sub` is the user id, not the email.** Emails change; the token should not stop
    identifying its subject when one does.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import User

_hasher = PasswordHash.recommended()

# tokenUrl is what makes the Authorize button in /docs post to the right endpoint.
_bearer = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# Verified against on the "user not found" path so that timing does not distinguish an
# unknown email from a wrong password. The plaintext behind it is irrelevant and no
# account uses it; what matters is that verifying it costs what a real verify costs.
_DUMMY_HASH = _hasher.hash("timing-equalisation-placeholder")

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password",
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _hasher.verify(plain, hashed)


def authenticate(db: Session, email: str, password: str) -> User:
    """Return the user for these credentials, or raise 401 without saying which half failed."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise _CREDENTIALS_ERROR
    if not verify_password(password, user.password_hash):
        raise _CREDENTIALS_ERROR
    return user


def create_access_token(user: User, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def current_user(
    token: str | None = Depends(_bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Resolve the bearer token to a live user row.

    The database lookup is not skippable: a token stays syntactically valid until it
    expires, so without it a deleted account would keep working for up to 12 hours.
    """
    if not token:
        raise _CREDENTIALS_ERROR
    try:
        # `algorithms` is a whitelist, not a hint. Trusting the token's own `alg` header
        # is how the classic "alg: none" and RS256-to-HS256 confusion attacks work.
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise _CREDENTIALS_ERROR from None

    user = db.get(User, user_id)
    if user is None:
        raise _CREDENTIALS_ERROR
    return user
