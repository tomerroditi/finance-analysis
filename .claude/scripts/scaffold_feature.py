#!/usr/bin/env python3
"""
Feature Scaffolder

Generates boilerplate files for a new backend feature following the
Routes -> Services -> Repositories architecture. The generated code is typed
and documented, so it passes the backend's ruff gate as-is.

Usage:
    python .claude/scripts/scaffold_feature.py <feature_name> [--output-dir <dir>]

Example:
    python .claude/scripts/scaffold_feature.py invoice
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

    @property
    def label(self) -> str:
        """Singular, human-readable name (``invoice item``)."""
        return self.singular.replace("_", " ")


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
    n = names
    return f'''"""{n.pascal_case} database model."""

from sqlalchemy import Column, Integer, String

from backend.constants.tables import Tables
from backend.models.base import Base, TimestampMixin


class {n.pascal_case}(Base, TimestampMixin):
    """One {n.label} record."""

    __tablename__ = Tables.{n.snake_case.upper()}.value

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)

    def __repr__(self) -> str:
        return f"<{n.pascal_case}(id={{self.id}}, name='{{self.name}}')>"
'''


def generate_repository(names: FeatureNames) -> str:
    """Generate repository file content."""
    n = names
    return f'''"""{n.pascal_case} data access."""

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.{n.snake_case} import {n.pascal_case}

COLUMNS = ["id", "name", "created_at", "updated_at"]


class {n.pascal_case}Repository:
    """Database operations for the ``{n.table_name}`` table."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_all(self) -> pd.DataFrame:
        """Return every record, with the canonical columns even when empty."""
        records = self.db.execute(select({n.pascal_case})).scalars().all()
        return pd.DataFrame(
            [{{col: getattr(r, col) for col in COLUMNS}} for r in records],
            columns=COLUMNS,
        )

    def get_by_id(self, item_id: int) -> {n.pascal_case} | None:
        """Return the record with ``item_id``, or ``None`` if absent."""
        return self.db.get({n.pascal_case}, item_id)

    def create(self, name: str, **fields: Any) -> {n.pascal_case}:
        """Insert a record and return it."""
        item = {n.pascal_case}(name=name, **fields)
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(self, item_id: int, **fields: Any) -> {n.pascal_case} | None:
        """Apply the non-``None`` ``fields`` to a record; ``None`` if absent."""
        item = self.db.get({n.pascal_case}, item_id)
        if item is None:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(item, key, value)
        self.db.commit()
        self.db.refresh(item)
        return item

    def delete(self, item_id: int) -> bool:
        """Delete a record; ``False`` if it did not exist."""
        item = self.db.get({n.pascal_case}, item_id)
        if item is None:
            return False
        self.db.delete(item)
        self.db.commit()
        return True
'''


def generate_service(names: FeatureNames) -> str:
    """Generate service file content."""
    n = names
    not_found = f'EntityNotFoundException(f"{n.pascal_case} {{item_id}} not found")'
    return f'''"""{n.pascal_case} business logic."""

from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.errors import EntityNotFoundException, ValidationException
from backend.models.{n.snake_case} import {n.pascal_case}
from backend.repositories.{n.snake_case}_repository import (
    {n.pascal_case}Repository,
)


class {n.pascal_case}Service:
    """Business operations on {n.label} records."""

    def __init__(self, db: Session) -> None:
        self.repo = {n.pascal_case}Repository(db)

    def get_all(self) -> pd.DataFrame:
        """Return every record."""
        return self.repo.get_all()

    def get_by_id(self, item_id: int) -> {n.pascal_case}:
        """Return one record.

        Raises
        ------
        EntityNotFoundException
            If no record has ``item_id``.
        """
        item = self.repo.get_by_id(item_id)
        if item is None:
            raise {not_found}
        return item

    def create(self, name: str, **fields: Any) -> {n.pascal_case}:
        """Validate and create a record.

        Raises
        ------
        ValidationException
            If ``name`` is blank.
        """
        if not name or not name.strip():
            raise ValidationException("Name is required")
        return self.repo.create(name=name.strip(), **fields)

    def update(self, item_id: int, **fields: Any) -> {n.pascal_case}:
        """Update a record.

        Raises
        ------
        EntityNotFoundException
            If no record has ``item_id``.
        """
        item = self.repo.update(item_id, **fields)
        if item is None:
            raise {not_found}
        return item

    def delete(self, item_id: int) -> None:
        """Delete a record.

        Raises
        ------
        EntityNotFoundException
            If no record has ``item_id``.
        """
        if not self.repo.delete(item_id):
            raise {not_found}
'''


def generate_route(names: FeatureNames) -> str:
    """Generate route file content."""
    n = names
    return f'''"""{n.pascal_case} API routes."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.models.{n.snake_case} import {n.pascal_case}
from backend.services.{n.snake_case}_service import {n.pascal_case}Service

router = APIRouter()


class {n.pascal_case}Create(BaseModel):
    """Body of a create request."""

    name: str


class {n.pascal_case}Update(BaseModel):
    """Body of an update request; omitted fields stay unchanged."""

    name: str | None = None


class {n.pascal_case}Response(BaseModel):
    """One {n.label} as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


@router.get("/")
def get_all(db: Session = Depends(get_database)) -> list[dict[str, Any]]:
    """List every {n.label}."""
    return {n.pascal_case}Service(db).get_all().to_dict(orient="records")


@router.get("/{{item_id}}", response_model={n.pascal_case}Response)
def get_by_id(item_id: int, db: Session = Depends(get_database)) -> {n.pascal_case}:
    """Get a single {n.label} by ID."""
    return {n.pascal_case}Service(db).get_by_id(item_id)


@router.post("/", response_model={n.pascal_case}Response)
def create(
    data: {n.pascal_case}Create, db: Session = Depends(get_database)
) -> {n.pascal_case}:
    """Create a new {n.label}."""
    return {n.pascal_case}Service(db).create(name=data.name)


@router.put("/{{item_id}}", response_model={n.pascal_case}Response)
def update(
    item_id: int,
    data: {n.pascal_case}Update,
    db: Session = Depends(get_database),
) -> {n.pascal_case}:
    """Update a {n.label}."""
    return {n.pascal_case}Service(db).update(
        item_id, **data.model_dump(exclude_unset=True)
    )


@router.delete("/{{item_id}}")
def delete(item_id: int, db: Session = Depends(get_database)) -> dict[str, str]:
    """Delete a {n.label}."""
    {n.pascal_case}Service(db).delete(item_id)
    return {{"status": "success"}}
'''


def generate_instructions(names: FeatureNames) -> str:
    """Generate setup instructions."""
    return f"""
=== SCAFFOLDING COMPLETE ===

Generated files for feature: {names.snake_case}

NEXT STEPS:

1. Add table name to backend/constants/tables.py:

   class Tables(Enum):
       ...
       {names.snake_case.upper()} = '{names.table_name}'

2. Export model from backend/models/__init__.py:

   from backend.models.{names.snake_case} import {names.pascal_case}

3. Register the router in ROUTERS in backend/router_registry.py (order = matching order):

   RouterMount("{names.snake_case}", "/api/{names.kebab_case}", "{names.pascal_case}"),

4. Update model columns in backend/models/{names.snake_case}.py

5. Update Pydantic models in backend/routes/{names.snake_case}.py

6. Add business logic to backend/services/{names.snake_case}_service.py

7. Keep it typed, documented and formatted:
   poetry run ruff check backend && poetry run ruff format backend

8. Restart the dev server to create the table:
   poetry run uvicorn backend.main:app --reload
"""


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

    print(f"\nScaffolding feature: {names.pascal_case}\n")

    for filepath, content in files:
        if filepath.exists():
            print(f"  SKIPPED (exists): {filepath}")
            continue

        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        print(f"  Created: {filepath}")

    print(generate_instructions(names))


def main() -> None:
    """Parse CLI arguments and scaffold (or dry-run) the feature."""
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
        print("\nWould create:")
        print(f"  - {args.output_dir}/models/{names.snake_case}.py")
        print(f"  - {args.output_dir}/repositories/{names.snake_case}_repository.py")
        print(f"  - {args.output_dir}/services/{names.snake_case}_service.py")
        print(f"  - {args.output_dir}/routes/{names.snake_case}.py")
        print(generate_instructions(names))
    else:
        scaffold_feature(args.feature_name, args.output_dir)


if __name__ == "__main__":
    main()
