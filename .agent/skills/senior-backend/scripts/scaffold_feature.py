#!/usr/bin/env python3
"""
Feature Scaffolder

Generates boilerplate files for a new backend feature following the
Routes → Services → Repositories architecture.

Usage:
    python scripts/scaffold_feature.py <feature_name> [--output-dir <dir>]

Example:
    python scripts/scaffold_feature.py invoice
    # Creates: invoice route, service, repository, and model files
"""

import argparse
from pathlib import Path
from typing import NamedTuple


class FeatureNames(NamedTuple):
    """Generated names for a feature."""

    snake_case: str  # invoice_items
    pascal_case: str  # InvoiceItems
    camel_case: str  # invoiceItems
    kebab_case: str  # invoice-items
    table_name: str  # invoice_items
    singular: str  # invoice_item


def to_pascal_case(snake: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in snake.split("_"))


def to_camel_case(snake: str) -> str:
    """Convert snake_case to camelCase."""
    words = snake.split("_")
    return words[0] + "".join(word.capitalize() for word in words[1:])


def to_kebab_case(snake: str) -> str:
    """Convert snake_case to kebab-case."""
    return snake.replace("_", "-")


def generate_names(feature_name: str) -> FeatureNames:
    """Generate all naming variations for a feature."""
    snake = feature_name.lower().replace("-", "_").replace(" ", "_")
    return FeatureNames(
        snake_case=snake,
        pascal_case=to_pascal_case(snake),
        camel_case=to_camel_case(snake),
        kebab_case=to_kebab_case(snake),
        table_name=snake if snake.endswith("s") else f"{snake}s",
        singular=snake.rstrip("s") if snake.endswith("s") else snake,
    )


def generate_model(names: FeatureNames) -> str:
    """Generate ORM model file content."""
    return f'''"""
{names.pascal_case} database model.
"""
from sqlalchemy import Column, Integer, String, Float, Boolean

from backend.models.base import Base, TimestampMixin
from backend.naming_conventions import Tables


class {names.pascal_case}(Base, TimestampMixin):
    """{names.pascal_case} database model."""

    __tablename__ = Tables.{names.snake_case.upper()}.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    # TODO: Add your columns here

    def __repr__(self):
        return f"<{names.pascal_case}(id={{self.id}}, name='{{self.name}}')>"
'''


def generate_repository(names: FeatureNames) -> str:
    """Generate repository file content."""
    return f'''"""
{names.pascal_case} data access.
"""
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import {names.pascal_case}


class {names.pascal_case}Repository:
    """{names.pascal_case} database operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """Get all records as DataFrame."""
        stmt = select({names.pascal_case})
        records = self.db.execute(stmt).scalars().all()

        if not records:
            return pd.DataFrame()

        data = [r.__dict__ for r in records]
        df = pd.DataFrame(data)
        if '_sa_instance_state' in df.columns:
            df = df.drop(columns=['_sa_instance_state'])
        return df

    def get_by_id(self, item_id: int) -> {names.pascal_case} | None:
        """Get a single record by ID."""
        return self.db.get({names.pascal_case}, item_id)

    def create(self, name: str, **kwargs) -> {names.pascal_case}:
        """Create a new record."""
        item = {names.pascal_case}(name=name, **kwargs)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(self, item_id: int, **fields) -> {names.pascal_case} | None:
        """Update a record."""
        item = self.db.get({names.pascal_case}, item_id)
        if not item:
            return None

        for key, value in fields.items():
            if value is not None:
                setattr(item, key, value)

        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self, item_id: int) -> bool:
        """Delete a record."""
        item = self.db.get({names.pascal_case}, item_id)
        if not item:
            return False

        self.db.delete(item)
        self.db.commit()
        return True
'''


def generate_service(names: FeatureNames) -> str:
    """Generate service file content."""
    return f'''"""
{names.pascal_case} business logic.
"""
import pandas as pd
from sqlalchemy.orm import Session

from backend.repositories.{names.snake_case}_repository import {names.pascal_case}Repository
from backend.errors import EntityNotFoundException, ValidationException


class {names.pascal_case}Service:
    """{names.pascal_case} business operations."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = {names.pascal_case}Repository(db)

    def get_all(self) -> pd.DataFrame:
        """Get all records."""
        return self.repo.get_all()

    def get_by_id(self, item_id: int):
        """Get a single record by ID."""
        item = self.repo.get_by_id(item_id)
        if not item:
            raise EntityNotFoundException(f"{names.pascal_case} {{item_id}} not found")
        return item

    def create(self, name: str, **kwargs):
        """Create a new record with validation."""
        # TODO: Add your business validation here
        if not name or not name.strip():
            raise ValidationException("Name is required")

        return self.repo.create(name=name.strip(), **kwargs)

    def update(self, item_id: int, **fields):
        """Update a record."""
        item = self.repo.update(item_id, **fields)
        if not item:
            raise EntityNotFoundException(f"{names.pascal_case} {{item_id}} not found")
        return item

    def delete(self, item_id: int) -> None:
        """Delete a record."""
        if not self.repo.delete(item_id):
            raise EntityNotFoundException(f"{names.pascal_case} {{item_id}} not found")
'''


def generate_route(names: FeatureNames) -> str:
    """Generate route file content."""
    return f'''"""
{names.pascal_case} API routes.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from backend.dependencies import get_database
from backend.services.{names.snake_case}_service import {names.pascal_case}Service


router = APIRouter()


# Pydantic models
class {names.pascal_case}Create(BaseModel):
    name: str
    # TODO: Add your fields here


class {names.pascal_case}Update(BaseModel):
    name: Optional[str] = None
    # TODO: Add your fields here


class {names.pascal_case}Response(BaseModel):
    id: int
    name: str
    # TODO: Add your fields here

    class Config:
        from_attributes = True


@router.get("/")
async def get_all(db: Session = Depends(get_database)):
    """Get all {names.snake_case}."""
    service = {names.pascal_case}Service(db)
    df = service.get_all()
    return df.to_dict(orient="records")


@router.get("/{{item_id}}", response_model={names.pascal_case}Response)
async def get_by_id(item_id: int, db: Session = Depends(get_database)):
    """Get a single {names.singular} by ID."""
    service = {names.pascal_case}Service(db)
    return service.get_by_id(item_id)


@router.post("/", response_model={names.pascal_case}Response)
async def create(data: {names.pascal_case}Create, db: Session = Depends(get_database)):
    """Create a new {names.singular}."""
    service = {names.pascal_case}Service(db)
    return service.create(name=data.name)


@router.put("/{{item_id}}", response_model={names.pascal_case}Response)
async def update(
    item_id: int,
    data: {names.pascal_case}Update,
    db: Session = Depends(get_database)
):
    """Update a {names.singular}."""
    service = {names.pascal_case}Service(db)
    return service.update(item_id, **data.model_dump(exclude_unset=True))


@router.delete("/{{item_id}}")
async def delete(item_id: int, db: Session = Depends(get_database)):
    """Delete a {names.singular}."""
    service = {names.pascal_case}Service(db)
    service.delete(item_id)
    return {{"status": "success"}}
'''


def generate_instructions(names: FeatureNames) -> str:
    """Generate setup instructions."""
    return f'''
=== SCAFFOLDING COMPLETE ===

Generated files for feature: {names.snake_case}

NEXT STEPS:

1. Add table name to backend/naming_conventions.py:

   class Tables(Enum):
       ...
       {names.snake_case.upper()} = '{names.table_name}'

2. Export model from backend/models/__init__.py:

   from backend.models.{names.snake_case} import {names.pascal_case}

3. Register router in backend/main.py:

   from backend.routes import {names.snake_case}
   app.include_router({names.snake_case}.router, prefix="/api/{names.kebab_case}", tags=["{names.pascal_case}"])

4. Update model columns in backend/models/{names.snake_case}.py

5. Update Pydantic models in backend/routes/{names.snake_case}.py

6. Add business logic to backend/services/{names.snake_case}_service.py

7. Restart the dev server to create the table:
   poetry run uvicorn backend.main:app --reload
'''


def scaffold_feature(feature_name: str, output_dir: Path) -> None:
    """Generate all files for a new feature."""
    names = generate_names(feature_name)

    files = [
        (output_dir / "models" / f"{names.snake_case}.py", generate_model(names)),
        (
            output_dir / "repositories" / f"{names.snake_case}_repository.py",
            generate_repository(names),
        ),
        (
            output_dir / "services" / f"{names.snake_case}_service.py",
            generate_service(names),
        ),
        (output_dir / "routes" / f"{names.snake_case}.py", generate_route(names)),
    ]

    print(f"\n🚀 Scaffolding feature: {names.pascal_case}\n")

    for filepath, content in files:
        if filepath.exists():
            print(f"⚠️  SKIPPED (exists): {filepath}")
            continue

        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        print(f"✅ Created: {filepath}")

    print(generate_instructions(names))


def main():
    parser = argparse.ArgumentParser(
        description="Scaffold a new backend feature (route, service, repository, model)"
    )
    parser.add_argument(
        "feature_name", help='Name of the feature (e.g., "invoice" or "payment_method")'
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path(__file__).parent.parent.parent / "backend",
        help="Backend directory path (default: ../../backend relative to script)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without writing files",
    )

    args = parser.parse_args()

    if args.dry_run:
        names = generate_names(args.feature_name)
        print(f"\nDry run for feature: {names.pascal_case}")
        print(f"\nWould create:")
        print(f"  - {args.output_dir}/models/{names.snake_case}.py")
        print(f"  - {args.output_dir}/repositories/{names.snake_case}_repository.py")
        print(f"  - {args.output_dir}/services/{names.snake_case}_service.py")
        print(f"  - {args.output_dir}/routes/{names.snake_case}.py")
        print(generate_instructions(names))
    else:
        scaffold_feature(args.feature_name, args.output_dir)


if __name__ == "__main__":
    main()
