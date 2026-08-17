"""Shopping list and recipes.

Two collections under one prefix because they are one screen, not because they are one
thing: a recipe outlives the week's shopping, and nothing joins them. They would split
cleanly the day either grows a reason to be addressed on its own.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MealIdea, Recipe, ShoppingItem, User
from app.schemas import (
    MealIdeaIn,
    MealIdeaOut,
    RecipeIn,
    RecipeOut,
    ShoppingItemIn,
    ShoppingItemOut,
    ShoppingItemPatch,
)
from app.security import current_user

router = APIRouter(prefix="/grocery", tags=["grocery"])


# --------------------------------------------------------------------- shopping


def _item_or_404(db: Session, item_id: int, user: User) -> ShoppingItem:
    item = db.scalar(
        select(ShoppingItem).where(ShoppingItem.id == item_id, ShoppingItem.user_id == user.id)
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Shopping item not found")
    return item


@router.get("/shopping", response_model=list[ShoppingItemOut])
def list_shopping(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[ShoppingItem]:
    stmt = (
        select(ShoppingItem)
        .where(ShoppingItem.user_id == user.id)
        .order_by(ShoppingItem.position, ShoppingItem.id)
    )
    return list(db.scalars(stmt))


@router.post("/shopping", response_model=ShoppingItemOut, status_code=status.HTTP_201_CREATED)
def create_shopping(
    payload: ShoppingItemIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ShoppingItem:
    # max()+1 rather than count(): after a deletion, count() would hand out a position
    # that an existing row already holds.
    highest = db.scalar(
        select(func.max(ShoppingItem.position)).where(ShoppingItem.user_id == user.id)
    )
    item = ShoppingItem(
        **payload.model_dump(), user_id=user.id, position=0 if highest is None else highest + 1
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/shopping/{item_id}", response_model=ShoppingItemOut)
def patch_shopping(
    item_id: int,
    payload: ShoppingItemPatch,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> ShoppingItem:
    item = _item_or_404(db, item_id, user)
    # exclude_unset so ticking `done` cannot blank a quantity the client never sent.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/shopping/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shopping(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    db.delete(_item_or_404(db, item_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/shopping", status_code=status.HTTP_204_NO_CONTENT)
def clear_shopping(
    done_only: bool = True,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    """Clear the list — bought items by default, everything with `done_only=false`.

    One statement rather than a loop of deletes: emptying a 40-item list should be one
    round trip, and the `user_id` predicate is what keeps a bulk delete scoped.
    """
    stmt = delete(ShoppingItem).where(ShoppingItem.user_id == user.id)
    if done_only:
        stmt = stmt.where(ShoppingItem.done.is_(True))
    db.execute(stmt)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------- recipes


def _recipe_or_404(db: Session, recipe_id: int, user: User) -> Recipe:
    recipe = db.scalar(
        select(Recipe).where(Recipe.id == recipe_id, Recipe.user_id == user.id)
    )
    if recipe is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found")
    return recipe


@router.get("/recipes", response_model=list[RecipeOut])
def list_recipes(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[Recipe]:
    stmt = select(Recipe).where(Recipe.user_id == user.id).order_by(Recipe.name, Recipe.id)
    return list(db.scalars(stmt))


@router.post("/recipes", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(
    payload: RecipeIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Recipe:
    recipe = Recipe(**payload.model_dump(), user_id=user.id)
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.put("/recipes/{recipe_id}", response_model=RecipeOut)
def replace_recipe(
    recipe_id: int,
    payload: RecipeIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Recipe:
    recipe = _recipe_or_404(db, recipe_id, user)
    for field, value in payload.model_dump().items():
        setattr(recipe, field, value)
    db.commit()
    db.refresh(recipe)
    return recipe


@router.delete("/recipes/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    db.delete(_recipe_or_404(db, recipe_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------- meal ideas


def _meal_idea_or_404(db: Session, idea_id: int, user: User) -> MealIdea:
    idea = db.scalar(
        select(MealIdea).where(MealIdea.id == idea_id, MealIdea.user_id == user.id)
    )
    if idea is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Meal idea not found")
    return idea


@router.get("/meal-ideas", response_model=list[MealIdeaOut])
def list_meal_ideas(
    db: Session = Depends(get_db), user: User = Depends(current_user)
) -> list[MealIdea]:
    return list(
        db.scalars(
            select(MealIdea)
            .where(MealIdea.user_id == user.id)
            .order_by(MealIdea.category, MealIdea.name, MealIdea.id)
        )
    )


@router.post("/meal-ideas", response_model=MealIdeaOut, status_code=status.HTTP_201_CREATED)
def create_meal_idea(
    payload: MealIdeaIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> MealIdea:
    idea = MealIdea(**payload.model_dump(), user_id=user.id)
    db.add(idea)
    db.commit()
    db.refresh(idea)
    return idea


@router.put("/meal-ideas/{idea_id}", response_model=MealIdeaOut)
def replace_meal_idea(
    idea_id: int,
    payload: MealIdeaIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> MealIdea:
    idea = _meal_idea_or_404(db, idea_id, user)
    for field, value in payload.model_dump().items():
        setattr(idea, field, value)
    db.commit()
    db.refresh(idea)
    return idea


@router.delete("/meal-ideas/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal_idea(
    idea_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    db.delete(_meal_idea_or_404(db, idea_id, user))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
