"""
Tagging API routes.

Provides endpoints for category and tag management.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.tagging_service import CategoriesTagsService

router = APIRouter()


class CategoryCreate(BaseModel):
    name: str
    tags: List[str] = []


class TagCreate(BaseModel):
    category: str
    name: str


class CategoryDelete(BaseModel):
    name: str


class TagDelete(BaseModel):
    category: str
    name: str


class TagRelocate(BaseModel):
    old_category: str
    new_category: str
    tag: str


class CategoryRename(BaseModel):
    new_name: str


class TagRename(BaseModel):
    new_name: str


@router.get("/categories")
async def get_categories(db: Session = Depends(get_database)):
    """Get all categories and their tags."""
    return CategoriesTagsService(db).get_categories_and_tags()


@router.post("/categories")
async def add_category(category: CategoryCreate, db: Session = Depends(get_database)):
    """Add a new category."""
    try:
        CategoriesTagsService(db).add_category(category.name, category.tags)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/categories/{name}")
async def delete_category(name: str, db: Session = Depends(get_database)):
    """Delete a category and all its tags.

    Transactions that were assigned to this category or any of its tags
    have their ``category`` and ``tag`` fields set to ``NULL`` in the DB.
    """
    try:
        CategoriesTagsService(db).delete_category(name)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tags")
async def create_tag(tag: TagCreate, db: Session = Depends(get_database)):
    """Add a tag to a category."""
    try:
        CategoriesTagsService(db).add_tag(tag.category, tag.name)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/tags/{category}/{name}")
async def delete_tag(category: str, name: str, db: Session = Depends(get_database)):
    """Delete a tag from a category.

    Transactions tagged with this tag have their ``tag`` field (and optionally
    ``category``) set to ``NULL`` in the DB.
    """
    try:
        CategoriesTagsService(db).delete_tag(category, name)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tags/relocate")
async def relocate_tag(data: TagRelocate, db: Session = Depends(get_database)):
    """Move a tag from one category to another.

    Updates the YAML config and re-categorises transactions that carry this
    tag so their ``category`` field reflects the new parent category.
    """
    try:
        CategoriesTagsService(db).reallocate_tag(
            data.old_category, data.new_category, data.tag
        )
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/categories/{name}")
async def rename_category(name: str, data: CategoryRename, db: Session = Depends(get_database)):
    """Rename a category and cascade the change across all tables."""
    from backend.errors import ValidationException

    success = CategoriesTagsService(db).rename_category(name, data.new_name)
    if not success:
        raise ValidationException(
            f"Cannot rename category '{name}'. It may be protected, not found, or '{data.new_name}' already exists."
        )
    return {"status": "success"}


@router.put("/tags/{category}/{name}")
async def rename_tag(category: str, name: str, data: TagRename, db: Session = Depends(get_database)):
    """Rename a tag and cascade the change across all tables."""
    from backend.errors import ValidationException

    success = CategoriesTagsService(db).rename_tag(category, name, data.new_name)
    if not success:
        raise ValidationException(
            f"Cannot rename tag '{name}'. It may be protected, not found, or '{data.new_name}' already exists in '{category}'."
        )
    return {"status": "success"}


@router.get("/icons")
async def get_category_icons(db: Session = Depends(get_database)):
    """Get category icons mapping."""
    return CategoriesTagsService(db).get_categories_icons()


@router.put("/icons/{category}")
async def update_category_icon(
    category: str, icon: str, db: Session = Depends(get_database)
):
    """Update a category's icon."""
    changed = CategoriesTagsService(db).update_category_icon(category, icon)
    return {"status": "success", "changed": changed}


@router.post("/add-new-credit-card-tags")
async def add_new_credit_card_tags(db: Session = Depends(get_database)):
    """Discover credit card accounts from transaction data and register them as tags.

    Scans credit card transactions for unique provider/account combinations and
    adds each as a tag under the ``Credit Cards`` category. These tags are later
    used by the auto-tag credit card bills feature to match bank debit lines to
    the corresponding monthly credit card charges.
    """
    CategoriesTagsService(db).add_new_credit_card_tags()
    return {"status": "success"}
