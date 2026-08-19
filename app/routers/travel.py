"""The trip: dates, a number plate, where you are staying, what to pack.

One trip per user, so the trip itself is addressed as `/travel` with no id — the same
shape as `/assets/goal`. Sub-resources hang off it. Every one of them looks the trip up
through `user_id` first, so a lodging id from another account is not reachable even by
guessing.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from html import unescape
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_calendar_client
from app.models import Lodging, PackingItem, PackingList, TravelBenefit, TravelExpense, Trip, User
from app.schemas import (
    CalendarLodgingSuggestion,
    LodgingIn,
    LodgingOut,
    PackingItemIn,
    PackingItemOut,
    PackingOrderIn,
    PackingListIn,
    PackingListOut,
    TravelBenefitIn,
    TravelBenefitOut,
    TravelExpenseIn,
    TravelExpenseOut,
    TripIn,
    TripOut,
)
from app.security import current_user
from app.services.calendar import CalendarClient

router = APIRouter(prefix="/travel", tags=["travel"])

_RECEIPT_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_RECEIPT_BYTES = 8 * 1024 * 1024
_TOTAL_LINE = re.compile(
    r"(?:grand\s*total|total|amount\s*due|balance\s*due|合計|總計|應付)"
    r"\D{0,20}(\d{1,7}[,.]\d{2})",
    re.I,
)
_MONEY = re.compile(r"(?<!\d)(\d{1,7}(?:[,.]\d{2}))(?!\d)")


def _receipt_ocr(data: bytes) -> str:
    """Use Tesseract when it is installed; uploads still work if OCR is unavailable."""
    try:
        import pytesseract
        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            return pytesseract.image_to_string(image, lang="eng+chi_tra", config="--psm 6")[:12000]
    except Exception:
        # A receipt must never become impossible to record merely because OCR is not
        # available on a developer machine. The review dialog makes that explicit.
        return ""


def _receipt_amount(text: str) -> Decimal:
    match = _TOTAL_LINE.search(text)
    if match is None:
        amounts = _MONEY.findall(text)
        if not amounts:
            return Decimal("0.00")
        match_text = amounts[-1]
    else:
        match_text = match.group(1)
    try:
        return Decimal(match_text.replace(",", ""))
    except Exception:
        return Decimal("0.00")


def _receipt_merchant(text: str, filename: str | None) -> str:
    for line in text.splitlines():
        clean = " ".join(line.split()).strip("-:=# ")
        if len(clean) >= 3 and not _MONEY.search(clean):
            return clean[:200]
    return (filename.rsplit(".", 1)[0] if filename else "收據")[:200] or "收據"


def _trip(db: Session, user: User) -> Trip | None:
    return db.scalar(select(Trip).where(Trip.user_id == user.id))


def _trip_or_create(db: Session, user: User) -> Trip:
    """Adding a hotel before filling in the dates is a reasonable order to work in,
    so the sub-resources create the trip rather than refusing until one exists."""
    trip = _trip(db, user)
    if trip is None:
        trip = Trip(user_id=user.id)
        db.add(trip)
        db.flush()
        db.add(PackingList(trip_id=trip.id, name="出門 Checklist", position=0))
        db.commit()
        db.refresh(trip)
    return trip


def _trip_or_404(db: Session, user: User) -> Trip:
    trip = _trip(db, user)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No trip yet")
    return trip


@router.get("", response_model=TripOut | None)
def get_trip(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Trip | None:
    """null rather than 404 when no trip is planned: "no trip" is a normal state of
    this resource, and the screen should not have to treat a 404 as success."""
    return _trip(db, user)


@router.put("", response_model=TripOut)
def set_trip(
    payload: TripIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Trip:
    trip = _trip_or_create(db, user)
    for field, value in payload.model_dump().items():
        setattr(trip, field, value)
    db.commit()
    db.refresh(trip)
    return trip


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def clear_trip(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    trip = _trip(db, user)
    if trip is not None:
        # Lodgings and packing items go with it: cascade="all, delete-orphan" on the
        # relationships, plus ON DELETE CASCADE in the schema for anything that reaches
        # the rows without going through the ORM.
        db.delete(trip)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------------------------------------------------- lodgings


@router.post("/lodgings", response_model=LodgingOut, status_code=status.HTTP_201_CREATED)
def add_lodging(
    payload: LodgingIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Lodging:
    trip = _trip_or_create(db, user)
    lodging = Lodging(**payload.model_dump(), trip_id=trip.id)
    db.add(lodging)
    db.commit()
    db.refresh(lodging)
    return lodging


@router.put("/lodgings/{lodging_id}", response_model=LodgingOut)
def replace_lodging(
    lodging_id: int,
    payload: LodgingIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Lodging:
    trip = _trip_or_404(db, user)
    # Scoped by trip_id as well as id. Without it, an id belonging to another account's
    # trip would be editable — ownership was only ever checked on the trip in the path.
    lodging = db.scalar(
        select(Lodging).where(Lodging.id == lodging_id, Lodging.trip_id == trip.id)
    )
    if lodging is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lodging not found")
    for field, value in payload.model_dump().items():
        setattr(lodging, field, value)
    db.commit()
    db.refresh(lodging)
    return lodging


@router.delete("/lodgings/{lodging_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lodging(
    lodging_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    trip = _trip_or_404(db, user)
    lodging = db.scalar(
        select(Lodging).where(Lodging.id == lodging_id, Lodging.trip_id == trip.id)
    )
    if lodging is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lodging not found")
    db.delete(lodging)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


_HOTEL_WORDS = re.compile(
    r"hotel|inn|marriott|hilton|hyatt|residence|suite|resort|reservation|stay|住宿|飯店",
    re.IGNORECASE,
)
_CONFIRMATION = re.compile(
    r"(?:confirmation(?:\s+(?:number|no\.?))?|conf(?:irmation)?\s*(?:#|no\.?)?|booking\s*(?:#|number)?|訂房(?:確認)?(?:號碼)?)\s*[:#-]?\s*([A-Z0-9-]{4,})",
    re.IGNORECASE,
)
_PHONE = re.compile(r"(?:\+?\d[\d(). -]{6,}\d)")
_HTML_TAG = re.compile(r"<[^>]+>")


def _calendar_text(value: str | None) -> str:
    """Turn HTML email-style calendar descriptions into readable plain text.

    Hotel confirmations often export an address as an ``<a>`` tag. Keeping the tag in
    the lodging notes both looks broken and leaves a huge tracking URL that can push
    the whole travel layout wider than the page.
    """
    return " ".join(_HTML_TAG.sub(" ", unescape(value or "")).split())


def _calendar_lodging(event) -> CalendarLodgingSuggestion | None:
    """Map the useful hotel fields Google exports in an iCal event into the stay form."""
    description = _calendar_text(event.description)
    location = _calendar_text(event.location)
    source = "\n".join(filter(None, [event.title, description, location]))
    if not _HOTEL_WORDS.search(source):
        return None

    name = re.sub(
        r"^(?:reservation|stay|hotel|住宿)\s*(?:at)?\s*[:\-]?\s*", "", event.title, flags=re.I
    )
    name = re.split(r"\s*,\s*(?:starts?|ends?)\s*:", name, maxsplit=1, flags=re.I)[0].strip()
    confirmation = _CONFIRMATION.search(source)
    phone = _PHONE.search(source)
    return CalendarLodgingSuggestion(
        name=(name or event.title)[:300],
        check_in=event.starts_at,
        check_out=event.ends_at,
        address=location[:500] or None,
        confirmation_number=confirmation.group(1)[:160] if confirmation else None,
        phone=phone.group(0)[:80] if phone else None,
        details=description[:500] or None,
    )


@router.get("/lodging-suggestions", response_model=list[CalendarLodgingSuggestion])
async def lodging_suggestions(
    check_in: date = Query(...),
    check_out: date = Query(...),
    calendar: CalendarClient = Depends(get_calendar_client),
) -> list[CalendarLodgingSuggestion]:
    """Offer hotel events that begin in the selected lodging period.

    The iCal feed is cached until the explicit Google Calendar refresh, so opening this
    form does not repeatedly fetch the Google Calendar.
    """
    if check_out < check_in:
        return []
    return [
        suggestion
        for event in await calendar.events_starting_between(check_in, check_out)
        if (suggestion := _calendar_lodging(event)) is not None
    ]


# --------------------------------------------------------------------- packing


def _default_packing_list(db: Session, trip: Trip) -> PackingList:
    packing_list = db.scalar(
        select(PackingList).where(PackingList.trip_id == trip.id).order_by(PackingList.position)
    )
    if packing_list is None:
        packing_list = PackingList(trip_id=trip.id, name="出門 Checklist", position=0)
        db.add(packing_list)
        db.flush()
    return packing_list


def _packing_list_or_404(db: Session, packing_list_id: int, user: User) -> PackingList:
    packing_list = db.scalar(
        select(PackingList)
        .join(Trip)
        .where(PackingList.id == packing_list_id, Trip.user_id == user.id)
    )
    if packing_list is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Packing checklist not found")
    return packing_list


@router.get("/packing-lists", response_model=list[PackingListOut])
def list_packing_lists(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[PackingList]:
    trip = _trip_or_404(db, user)
    return list(
        db.scalars(
            select(PackingList)
            .where(PackingList.trip_id == trip.id)
            .order_by(PackingList.position, PackingList.id)
        )
    )


@router.post("/packing-lists", response_model=PackingListOut, status_code=status.HTTP_201_CREATED)
def create_packing_list(
    payload: PackingListIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PackingList:
    trip = _trip_or_create(db, user)
    highest = db.scalar(select(func.max(PackingList.position)).where(PackingList.trip_id == trip.id))
    packing_list = PackingList(
        trip_id=trip.id, name=payload.name, position=0 if highest is None else highest + 1
    )
    db.add(packing_list)
    db.commit()
    db.refresh(packing_list)
    return packing_list


@router.put("/packing-lists/{packing_list_id}", response_model=PackingListOut)
def replace_packing_list(
    packing_list_id: int,
    payload: PackingListIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PackingList:
    packing_list = _packing_list_or_404(db, packing_list_id, user)
    packing_list.name = payload.name
    db.commit()
    db.refresh(packing_list)
    return packing_list


@router.delete("/packing-lists/{packing_list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_packing_list(
    packing_list_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    db.delete(_packing_list_or_404(db, packing_list_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/packing-lists/{packing_list_id}/items/order", response_model=list[PackingItemOut])
def reorder_packing_items(
    packing_list_id: int,
    payload: PackingOrderIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[PackingItem]:
    """Persist a checklist's complete drag/drop order.

    Requiring every current item prevents a stale browser tab from silently assigning
    arbitrary positions to a different person's item, or from losing a row added in
    another tab.
    """
    packing_list = _packing_list_or_404(db, packing_list_id, user)
    items = list(
        db.scalars(
            select(PackingItem)
            .where(PackingItem.packing_list_id == packing_list.id)
            .order_by(PackingItem.position, PackingItem.id)
        )
    )
    requested = payload.ids
    if len(requested) != len(set(requested)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Duplicate packing item id")
    by_id = {item.id: item for item in items}
    if set(requested) != set(by_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The request does not match this checklist's current items; reload and try again",
        )
    for position, item_id in enumerate(requested):
        by_id[item_id].position = position
    db.commit()
    return [by_id[item_id] for item_id in requested]


@router.post("/packing", response_model=PackingItemOut, status_code=status.HTTP_201_CREATED)
def add_packing_item(
    payload: PackingItemIn,
    packing_list_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PackingItem:
    trip = _trip_or_create(db, user)
    packing_list = _packing_list_or_404(db, packing_list_id, user) if packing_list_id else _default_packing_list(db, trip)
    if packing_list.trip_id != trip.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Packing checklist not found")
    highest = db.scalar(
        select(func.max(PackingItem.position)).where(PackingItem.packing_list_id == packing_list.id)
    )
    item = PackingItem(
        **payload.model_dump(), trip_id=trip.id, packing_list_id=packing_list.id,
        position=0 if highest is None else highest + 1
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/packing/{item_id}", response_model=PackingItemOut)
def toggle_packing_item(
    item_id: int,
    done: bool,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> PackingItem:
    trip = _trip_or_404(db, user)
    item = db.scalar(
        select(PackingItem).where(PackingItem.id == item_id, PackingItem.trip_id == trip.id)
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Packing item not found")
    item.done = done
    db.commit()
    db.refresh(item)
    return item


@router.delete("/packing/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_packing_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    trip = _trip_or_404(db, user)
    item = db.scalar(
        select(PackingItem).where(PackingItem.id == item_id, PackingItem.trip_id == trip.id)
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Packing item not found")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------- expenses


def _expense_or_404(db: Session, expense_id: int, user: User) -> TravelExpense:
    trip = _trip_or_404(db, user)
    expense = db.scalar(
        select(TravelExpense).where(
            TravelExpense.id == expense_id, TravelExpense.trip_id == trip.id
        )
    )
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Travel expense not found")
    return expense


@router.post("/expenses", response_model=TravelExpenseOut, status_code=status.HTTP_201_CREATED)
def create_expense(
    payload: TravelExpenseIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TravelExpense:
    expense = TravelExpense(**payload.model_dump(), trip_id=_trip_or_create(db, user).id)
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.post("/expenses/scan", response_model=TravelExpenseOut, status_code=status.HTTP_201_CREATED)
async def scan_receipt(
    receipt: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TravelExpense:
    """Store one receipt and return an editable OCR draft.

    The browser opens the edit dialog immediately after this response. A zero amount
    is deliberately allowed for an unclear scan so no guessed charge is ever silently
    added to the trip total.
    """
    if receipt.content_type not in _RECEIPT_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a JPG, PNG, or WebP receipt"
        )
    data = await receipt.read(_MAX_RECEIPT_BYTES + 1)
    if not data or len(data) > _MAX_RECEIPT_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Receipt image must be 8 MB or smaller"
        )
    ocr_text = _receipt_ocr(data)
    expense = TravelExpense(
        trip_id=_trip_or_create(db, user).id,
        merchant=_receipt_merchant(ocr_text, receipt.filename),
        amount=_receipt_amount(ocr_text),
        spent_at=date.today(),
        receipt_filename=(receipt.filename or "receipt")[:255],
        receipt_media_type=receipt.content_type,
        receipt_data=data,
        ocr_text=ocr_text or None,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.put("/expenses/{expense_id}", response_model=TravelExpenseOut)
def replace_expense(
    expense_id: int,
    payload: TravelExpenseIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TravelExpense:
    expense = _expense_or_404(db, expense_id, user)
    for field, value in payload.model_dump().items():
        setattr(expense, field, value)
    db.commit()
    db.refresh(expense)
    return expense


@router.get("/expenses/{expense_id}/receipt")
def get_receipt(
    expense_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    expense = _expense_or_404(db, expense_id, user)
    if expense.receipt_data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No receipt image")
    return Response(
        content=expense.receipt_data,
        media_type=expense.receipt_media_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f'inline; filename="{expense.receipt_filename or "receipt"}"'
            )
        },
    )


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    db.delete(_expense_or_404(db, expense_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------- travel benefits


def _benefit_or_404(db: Session, benefit_id: int, user: User) -> TravelBenefit:
    benefit = db.scalar(
        select(TravelBenefit).where(
            TravelBenefit.id == benefit_id, TravelBenefit.user_id == user.id
        )
    )
    if benefit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Travel benefit not found")
    return benefit


@router.get("/benefits", response_model=list[TravelBenefitOut])
def list_benefits(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[TravelBenefit]:
    return list(
        db.scalars(
            select(TravelBenefit)
            .where(TravelBenefit.user_id == user.id)
            .order_by(
                TravelBenefit.expires_at.is_(None), TravelBenefit.expires_at, TravelBenefit.id
            )
        )
    )


@router.post("/benefits", response_model=TravelBenefitOut, status_code=status.HTTP_201_CREATED)
def create_benefit(
    payload: TravelBenefitIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TravelBenefit:
    benefit = TravelBenefit(**payload.model_dump(), user_id=user.id)
    db.add(benefit)
    db.commit()
    db.refresh(benefit)
    return benefit


@router.put("/benefits/{benefit_id}", response_model=TravelBenefitOut)
def replace_benefit(
    benefit_id: int,
    payload: TravelBenefitIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> TravelBenefit:
    benefit = _benefit_or_404(db, benefit_id, user)
    for field, value in payload.model_dump().items():
        setattr(benefit, field, value)
    db.commit()
    db.refresh(benefit)
    return benefit


@router.delete("/benefits/{benefit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_benefit(
    benefit_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    db.delete(_benefit_or_404(db, benefit_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
