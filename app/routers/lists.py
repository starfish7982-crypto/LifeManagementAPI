"""User-defined tables.

The generic half of the app: subscriptions, warranties, budgets, recipe ideas — data
whose shape the owner decides rather than the schema. A list owns its column headings;
each row holds a positional array of values lined up against them.

The one invariant the database cannot express is that a row has exactly as many values
as its list has columns — no SQL constraint reaches across to the parent's JSON array.
So it is enforced here, on every write, by `_check_width`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ListItem, ListTable, User
from app.schemas import ListIn, ListItemIn, ListItemOut, ListOut
from app.security import current_user

router = APIRouter(prefix="/lists", tags=["lists"])


def _get_or_404(db: Session, list_id: int, user: User) -> ListTable:
    table = db.scalar(
        select(ListTable).where(ListTable.id == list_id, ListTable.user_id == user.id)
    )
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    return table


def _check_width(table: ListTable, values: list[str]) -> None:
    """A row must line up with its headings.

    422, not 400: this is a validation failure about the request body, and it is the
    status FastAPI already uses for everything Pydantic rejects. A client that gets a
    different code for the same class of mistake has to handle two.
    """
    if len(values) != len(table.columns):
        # Literal 422 rather than the Starlette constant: it was renamed from
        # HTTP_422_UNPROCESSABLE_ENTITY to ..._CONTENT, so naming it either way pins
        # this file to a version range. The number has not moved since RFC 4918.
        raise HTTPException(
            422,
            f"Expected {len(table.columns)} values to match the list's columns, got {len(values)}",
        )


def _next_position(db: Session, list_id: int) -> int:
    highest = db.scalar(
        select(func.max(ListItem.position)).where(ListItem.list_id == list_id)
    )
    return 0 if highest is None else highest + 1


# ----------------------------------------------------------------------------- lists


@router.get("", response_model=list[ListOut])
def list_lists(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[ListTable]:
    # Ordered by explicit position, then id so the order is total: two lists sharing a
    # position must still come back in the same sequence on every request.
    stmt = (
        select(ListTable)
        .where(ListTable.user_id == user.id)
        .order_by(ListTable.position, ListTable.id)
    )
    return list(db.scalars(stmt))


@router.post("", response_model=ListOut, status_code=status.HTTP_201_CREATED)
def create_list(
    payload: ListIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ListTable:
    clash = db.scalar(
        select(ListTable).where(ListTable.user_id == user.id, ListTable.name == payload.name)
    )
    if clash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A list named {payload.name!r} exists")

    table = ListTable(**payload.model_dump(), user_id=user.id)
    db.add(table)
    db.commit()
    db.refresh(table)
    return table


@router.get("/{list_id}", response_model=ListOut)
def get_list(
    list_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ListTable:
    return _get_or_404(db, list_id, user)


@router.put("/{list_id}", response_model=ListOut)
def replace_list(
    list_id: int,
    payload: ListIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ListTable:
    """Rename, re-icon, reorder, or change the columns.

    Changing the column count would strand every existing row at the wrong width, so it
    is refused while the list has rows. Widening or narrowing a populated table is a
    data migration — which values move where, what fills the new cell — and silently
    guessing is worse than saying no.
    """
    table = _get_or_404(db, list_id, user)

    if len(payload.columns) != len(table.columns) and table.items:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot change the number of columns while the list has {len(table.items)} "
            "rows; delete the rows first",
        )

    clash = db.scalar(
        select(ListTable).where(
            ListTable.user_id == user.id,
            ListTable.name == payload.name,
            ListTable.id != list_id,
        )
    )
    if clash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A list named {payload.name!r} exists")

    for field, value in payload.model_dump().items():
        setattr(table, field, value)
    db.commit()
    db.refresh(table)
    return table


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(
    list_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    db.delete(_get_or_404(db, list_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ----------------------------------------------------------------------------- rows


@router.post("/{list_id}/items", response_model=ListItemOut, status_code=status.HTTP_201_CREATED)
def create_item(
    list_id: int,
    payload: ListItemIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ListItem:
    table = _get_or_404(db, list_id, user)
    _check_width(table, payload.values)

    item = ListItem(
        list_id=table.id, values=payload.values, position=_next_position(db, table.id)
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/{list_id}/items/{item_id}", response_model=ListItemOut)
def replace_item(
    list_id: int,
    item_id: int,
    payload: ListItemIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ListItem:
    table = _get_or_404(db, list_id, user)
    _check_width(table, payload.values)

    # Scoped by list_id as well as id: without it, /lists/1/items/99 would happily edit
    # a row belonging to list 2 — including another user's, since ownership was only
    # ever checked on list 1.
    item = db.scalar(
        select(ListItem).where(ListItem.id == item_id, ListItem.list_id == table.id)
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Row not found")

    item.values = payload.values
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{list_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    list_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    table = _get_or_404(db, list_id, user)
    item = db.scalar(
        select(ListItem).where(ListItem.id == item_id, ListItem.list_id == table.id)
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Row not found")

    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
