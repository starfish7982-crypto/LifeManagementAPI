"""Registration, login, and "who am I".

Login takes form-encoded credentials rather than JSON because that is what the OAuth2
password flow specifies, and following it is what makes the Authorize button in /docs
work without custom JavaScript. The field is named `username` for the same reason; it
carries an email here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import User
from app.schemas import Token, UserCreate, UserOut
from app.security import authenticate, create_access_token, current_user, hash_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        # This does leak that the address is registered. Every alternative leaks it
        # somewhere else (the password-reset flow, or a login that now succeeds), and
        # a signup form that cannot say "you already have an account" is a worse
        # product for a real cost that is close to zero here.
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
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
