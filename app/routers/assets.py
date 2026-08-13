"""Asset snapshot endpoints.

Resource shape: /assets/snapshots is the collection, a snapshot owns its items, and
/assets/snapshots/{id}/categories is a computed sub-resource. Items are not exposed
as a top-level collection because an item has no meaning outside its snapshot.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AssetGoal, AssetItem, AssetSnapshot, User
from app.schemas import (
    AssetGoalIn,
    AssetGoalOut,
    AssetSnapshotIn,
    AssetSnapshotOut,
    CategoryTotal,
)
from app.security import current_user

router = APIRouter(prefix="/assets", tags=["assets"])


def _get_or_404(db: Session, snapshot_id: int, user: User) -> AssetSnapshot:
    """Fetch a snapshot the caller owns; another account's id is indistinguishable
    from one that does not exist. See the same helper in `todos.py` for why."""
    snapshot = db.scalar(
        select(AssetSnapshot).where(
            AssetSnapshot.id == snapshot_id, AssetSnapshot.user_id == user.id
        )
    )
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Snapshot not found")
    return snapshot


@router.get("/categories", response_model=list[str])
def list_categories(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[str]:
    """Every category this user has actually used, for the UI's dropdown.

    Derived from the snapshots rather than stored as its own table. A category list is
    only ever a convenience for data entry, and a stored one immediately raises
    questions the feature does not need answers to: what happens when the last item in
    a category is deleted, can a category be renamed across history, what does an
    unused category mean. Deriving it makes all three unanswerable by construction.

    The cost is that a category cannot be created before it is used — which is the
    behaviour the UI wants anyway, since the field is free text.
    """
    rows = db.execute(
        select(AssetItem.category)
        .join(AssetSnapshot, AssetItem.snapshot_id == AssetSnapshot.id)
        .where(AssetSnapshot.user_id == user.id)
        .group_by(AssetItem.category)
        .order_by(func.count().desc(), AssetItem.category)
    ).all()
    return [c for (c,) in rows]


# ----------------------------------------------------------------------------- goal


@router.get("/goal", response_model=AssetGoalOut | None)
def get_goal(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AssetGoal | None:
    """Returns null rather than 404 when no goal is set.

    "You have not set a goal" is a normal state of this resource, not a missing
    resource, and the dashboard should not have to treat a 404 as success.
    """
    return db.scalar(select(AssetGoal).where(AssetGoal.user_id == user.id))


@router.put("/goal", response_model=AssetGoalOut)
def set_goal(
    payload: AssetGoalIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AssetGoal:
    """Upsert. PUT rather than POST because there is at most one goal per user, so the
    request is idempotent: sending it twice leaves the same single row."""
    goal = db.scalar(select(AssetGoal).where(AssetGoal.user_id == user.id))
    if goal is None:
        goal = AssetGoal(**payload.model_dump(), user_id=user.id)
        db.add(goal)
    else:
        for field, value in payload.model_dump().items():
            setattr(goal, field, value)
    db.commit()
    db.refresh(goal)
    return goal


@router.delete("/goal", status_code=status.HTTP_204_NO_CONTENT)
def clear_goal(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    goal = db.scalar(select(AssetGoal).where(AssetGoal.user_id == user.id))
    if goal is not None:
        db.delete(goal)
        db.commit()
    # 204 whether or not there was a goal: DELETE is idempotent, and the caller's
    # intent ("there should be no goal") is satisfied either way.
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------------ snapshots


@router.get("/snapshots", response_model=list[AssetSnapshotOut])
def list_snapshots(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    since: date | None = Query(None, description="Only months on or after this date"),
) -> list[AssetSnapshot]:
    # Pagination is capped server-side. An unbounded list endpoint is a denial-of-service
    # vector once the table grows, and clients always eventually ask for everything.
    stmt = (
        select(AssetSnapshot)
        .where(AssetSnapshot.user_id == user.id)
        .order_by(AssetSnapshot.month.desc())
    )
    if since is not None:
        stmt = stmt.where(AssetSnapshot.month >= since.replace(day=1))
    return list(db.scalars(stmt.limit(limit).offset(offset)))


@router.post("/snapshots", response_model=AssetSnapshotOut, status_code=status.HTTP_201_CREATED)
def create_snapshot(
    payload: AssetSnapshotIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AssetSnapshot:
    existing = db.scalar(
        select(AssetSnapshot).where(
            AssetSnapshot.user_id == user.id, AssetSnapshot.month == payload.month
        )
    )
    if existing is not None:
        # 409, not 400: the request is well-formed, it conflicts with current state.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"A snapshot for {payload.month:%Y-%m} already exists (id={existing.id})",
        )

    snapshot = AssetSnapshot(month=payload.month, note=payload.note, user_id=user.id)
    snapshot.items = [AssetItem(**item.model_dump()) for item in payload.items]
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.get("/snapshots/{snapshot_id}", response_model=AssetSnapshotOut)
def get_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AssetSnapshot:
    return _get_or_404(db, snapshot_id, user)


@router.put("/snapshots/{snapshot_id}", response_model=AssetSnapshotOut)
def replace_snapshot(
    snapshot_id: int,
    payload: AssetSnapshotIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> AssetSnapshot:
    snapshot = _get_or_404(db, snapshot_id, user)

    clash = db.scalar(
        select(AssetSnapshot).where(
            AssetSnapshot.user_id == user.id,
            AssetSnapshot.month == payload.month,
            AssetSnapshot.id != snapshot_id,
        )
    )
    if clash is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Another snapshot already uses that month")

    snapshot.month = payload.month
    snapshot.note = payload.note
    # delete-orphan on the relationship turns this reassignment into DELETEs for the
    # rows that are no longer referenced. Without it they would be left with a NULL FK.
    snapshot.items = [AssetItem(**item.model_dump()) for item in payload.items]
    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.delete("/snapshots/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    snapshot = _get_or_404(db, snapshot_id, user)
    db.delete(snapshot)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/snapshots/{snapshot_id}/categories", response_model=list[CategoryTotal])
def category_breakdown(
    snapshot_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[CategoryTotal]:
    # Ownership is checked before the aggregate runs. The GROUP BY below filters on
    # snapshot_id alone, which is only safe because this line already proved the
    # snapshot belongs to the caller.
    _get_or_404(db, snapshot_id, user)
    # Aggregated in SQL rather than in Python: the database can answer this from the
    # (snapshot_id, category) index without materialising every row.
    rows = db.execute(
        select(AssetItem.category, func.sum(AssetItem.amount))
        .where(AssetItem.snapshot_id == snapshot_id)
        .group_by(AssetItem.category)
        .order_by(func.sum(AssetItem.amount).desc())
    ).all()
    return [CategoryTotal(category=c, total=t) for c, t in rows]
