"""Ideas: the scratchpad. Newest first, because that is the one you just wrote."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Idea, User
from app.schemas import IdeaIn, IdeaOut
from app.security import current_user

router = APIRouter(prefix="/ideas", tags=["ideas"])


def _get_or_404(db: Session, idea_id: int, user: User) -> Idea:
    idea = db.scalar(select(Idea).where(Idea.id == idea_id, Idea.user_id == user.id))
    if idea is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Idea not found")
    return idea


@router.get("", response_model=list[IdeaOut])
def list_ideas(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[Idea]:
    stmt = (
        select(Idea)
        .where(Idea.user_id == user.id)
        # id as the tiebreaker: two ideas captured in the same second would otherwise
        # come back in whatever order the database felt like, and flip between loads.
        .order_by(Idea.created_at.desc(), Idea.id.desc())
    )
    return list(db.scalars(stmt))


@router.post("", response_model=IdeaOut, status_code=status.HTTP_201_CREATED)
def create_idea(
    payload: IdeaIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Idea:
    idea = Idea(**payload.model_dump(), user_id=user.id)
    db.add(idea)
    db.commit()
    db.refresh(idea)
    return idea


@router.put("/{idea_id}", response_model=IdeaOut)
def replace_idea(
    idea_id: int,
    payload: IdeaIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Idea:
    idea = _get_or_404(db, idea_id, user)
    for field, value in payload.model_dump().items():
        setattr(idea, field, value)
    db.commit()
    db.refresh(idea)
    return idea


@router.delete("/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_idea(
    idea_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    db.delete(_get_or_404(db, idea_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
