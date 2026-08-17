"""Registration, login, and "who am I".

Login takes form-encoded credentials rather than JSON because that is what the OAuth2
password flow specifies, and following it is what makes the Authorize button in /docs
work without custom JavaScript. The field is named `username` by the standard and it
also carries the application's account name.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import User
from app.schemas import PasswordChange, Token, UserCreate, UserOut
from app.security import (
    authenticate,
    create_access_token,
    current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    existing = db.scalar(select(User).where(User.username == payload.username))
    if existing is not None:
        # This does leak that the address is registered. Every alternative leaks it
        # somewhere else (the password-reset flow, or a login that now succeeds), and
        # a signup form that cannot say "you already have an account" is a worse
        # product for a real cost that is close to zero here.
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already registered")

    user = User(username=payload.username, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Token:
    user = authenticate(db, form.username, form.password)
    return Token(
        access_token=create_access_token(user, settings),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@router.post("/password", response_model=Token)
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> Token:
    """Rotate the password, keeping the account and everything in it.

    Deleting and re-registering is the other way to get a new password, and it takes
    the data with it. That is a bad enough outcome that "I have to change my password"
    should not lead there.

    Returns a fresh token. Tokens issued before the change stay valid until they expire
    — they are signed, not stored, so there is nothing to revoke. Properly invalidating
    them needs either a token version column checked on every request or a deny-list
    with its own storage; both are the right answer for a service with real users and
    more than this one needs. The 12-hour expiry is the bound in the meantime, and this
    comment is here so that limit is a known one rather than an assumed absence.
    """
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return Token(
        access_token=create_access_token(user, settings),
        expires_in=settings.access_token_ttl_minutes * 60,
    )
