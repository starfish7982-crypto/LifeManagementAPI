"""Todo endpoints. PATCH is partial by design: the UI toggles `done` alone."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Todo, User
from app.schemas import TodoIn, TodoOrderIn, TodoOut, TodoPatch
from app.security import current_user

router = APIRouter(prefix="/todos", tags=["todos"])


def _get_or_404(db: Session, todo_id: int, user: User) -> Todo:
    """Fetch a todo the caller owns.

    Someone else's id returns 404 rather than 403. 403 would confirm that the row
    exists, which turns sequential ids into a probe for how much data other accounts
    hold. "Not found" is true from the caller's point of view: they cannot address it.
    """
    todo = db.scalar(select(Todo).where(Todo.id == todo_id, Todo.user_id == user.id))
    if todo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Todo not found")
    return todo


@router.get("", response_model=list[TodoOut])
def list_todos(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    done: bool | None = Query(None),
    due_before: date | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[Todo]:
    stmt = select(Todo).where(Todo.user_id == user.id)
    if done is not None:
        stmt = stmt.where(Todo.done.is_(done))
    if due_before is not None:
        stmt = stmt.where(Todo.due_date.is_not(None), Todo.due_date <= due_before)
    stmt = stmt.order_by(Todo.bucket, Todo.position, Todo.id)
    return list(db.scalars(stmt.limit(limit).offset(offset)))


@router.post("", response_model=TodoOut, status_code=status.HTTP_201_CREATED)
def create_todo(
    payload: TodoIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Todo:
    # Ownership comes from the token, never from the request body. A `user_id` field on
    # TodoIn would let any caller write rows into any account.
    # Position is allocated inside the selected lane.  Count() would reuse a deleted
    # slot, so use max()+1 just as the other reorderable lists do.
    highest = db.scalar(
        select(func.max(Todo.position)).where(
            Todo.user_id == user.id, Todo.bucket == payload.bucket
        )
    )
    todo = Todo(
        **payload.model_dump(),
        user_id=user.id,
        position=0 if highest is None else highest + 1,
    )
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo


@router.put("/order", response_model=list[TodoOut])
def reorder_todos(
    payload: TodoOrderIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[Todo]:
    """Persist a lane's complete drag/drop order.

    The full-set check prevents a stale page from accidentally moving an item the
    user cannot see to an arbitrary position.
    """
    rows = list(
        db.scalars(
            select(Todo)
            .where(Todo.user_id == user.id, Todo.bucket == payload.bucket)
            .order_by(Todo.position, Todo.id)
        )
    )
    by_id = {row.id: row for row in rows}
    if len(payload.ids) != len(set(payload.ids)) or set(payload.ids) != set(by_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Order must include this lane")

    for position, todo_id in enumerate(payload.ids):
        by_id[todo_id].position = position
    db.commit()
    return [by_id[todo_id] for todo_id in payload.ids]


@router.patch("/{todo_id}", response_model=TodoOut)
def patch_todo(
    todo_id: int,
    payload: TodoPatch,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Todo:
    todo = _get_or_404(db, todo_id, user)
    # exclude_unset distinguishes "field omitted" from "field set to null". Without it,
    # toggling `done` would silently wipe `due_date`.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(todo, field, value)
    db.commit()
    db.refresh(todo)
    return todo


@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(
    todo_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    db.delete(_get_or_404(db, todo_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
