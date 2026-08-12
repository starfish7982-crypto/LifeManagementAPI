"""Todo endpoints. PATCH is partial by design: the UI toggles `done` alone."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Todo
from app.schemas import TodoIn, TodoOut, TodoPatch
from app.security import require_api_key

router = APIRouter(prefix="/todos", tags=["todos"], dependencies=[Depends(require_api_key)])


def _get_or_404(db: Session, todo_id: int) -> Todo:
    todo = db.get(Todo, todo_id)
    if todo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Todo not found")
    return todo


@router.get("", response_model=list[TodoOut])
def list_todos(
    db: Session = Depends(get_db),
    done: bool | None = Query(None),
    due_before: date | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[Todo]:
    stmt = select(Todo)
    if done is not None:
        stmt = stmt.where(Todo.done.is_(done))
    if due_before is not None:
        stmt = stmt.where(Todo.due_date.is_not(None), Todo.due_date <= due_before)
    stmt = stmt.order_by(Todo.due_date.is_(None), Todo.due_date, Todo.id)
    return list(db.scalars(stmt.limit(limit).offset(offset)))


@router.post("", response_model=TodoOut, status_code=status.HTTP_201_CREATED)
def create_todo(payload: TodoIn, db: Session = Depends(get_db)) -> Todo:
    todo = Todo(**payload.model_dump())
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo


@router.patch("/{todo_id}", response_model=TodoOut)
def patch_todo(todo_id: int, payload: TodoPatch, db: Session = Depends(get_db)) -> Todo:
    todo = _get_or_404(db, todo_id)
    # exclude_unset distinguishes "field omitted" from "field set to null". Without it,
    # toggling `done` would silently wipe `due_date`.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(todo, field, value)
    db.commit()
    db.refresh(todo)
    return todo


@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(todo_id: int, db: Session = Depends(get_db)) -> Response:
    db.delete(_get_or_404(db, todo_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
