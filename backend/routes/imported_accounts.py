"""API routes for file-import data sources."""

import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.dependencies import get_database
from backend.services.imported_accounts_service import ImportedAccountsService

router = APIRouter()


class CreateRequest(BaseModel):
    service: str
    provider: str
    account_name: str
    mapping: dict[str, Any]


class UpdateMappingRequest(BaseModel):
    mapping: dict[str, Any]


_TEMPLATE_CSV = (
    "date,description,amount,category,tag\n"
    "2026-03-01,Coffee shop,-12.50,Food,Coffee\n"
    "2026-03-03,Salary,8500.00,Salary,Salary\n"
    "2026-03-05,Refund,45.00,Food,Groceries\n"
    "2026-03-07,Gym membership,-180.00,,\n"
    "2026-03-10,Withdrawal,-200.00,,\n"
)


@router.get("/")
async def list_imported_accounts(
    db: Session = Depends(get_database),
) -> list[dict[str, Any]]:
    """List all file-import accounts."""
    service = ImportedAccountsService(db)
    return [dto.__dict__ for dto in service.list_accounts()]


@router.post("/")
async def create_imported_account(
    req: CreateRequest,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Create a new file-import account."""
    service = ImportedAccountsService(db)
    try:
        dto = service.create(
            service_type=req.service,
            provider=req.provider,
            account_name=req.account_name,
            mapping=req.mapping,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return dto.__dict__


@router.put("/{account_id}")
async def update_imported_account_mapping(
    account_id: int,
    req: UpdateMappingRequest,
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Update only the saved mapping for an account."""
    service = ImportedAccountsService(db)
    try:
        dto = service.update_mapping(account_id, req.mapping)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return dto.__dict__


@router.delete("/{account_id}")
async def delete_imported_account(
    account_id: int,
    db: Session = Depends(get_database),
) -> dict[str, str]:
    """Delete an imported account + cascade-delete its transactions."""
    service = ImportedAccountsService(db)
    if not service.delete(account_id):
        raise HTTPException(status_code=404, detail="Imported account not found")
    return {"status": "deleted"}


@router.post("/{account_id}/upload")
async def upload_file(
    account_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_database),
) -> dict[str, int]:
    """Run an import against the saved mapping for ``account_id``."""
    raw = await file.read()
    service = ImportedAccountsService(db)
    try:
        return service.import_file(
            account_id=account_id,
            raw=raw,
            filename=file.filename or "upload",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preview")
async def preview(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    db: Session = Depends(get_database),
) -> dict[str, Any]:
    """Preview the first 5 mapped rows. Does not persist."""
    try:
        mapping_dict = json.loads(mapping)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="mapping is not valid JSON")
    raw = await file.read()
    service = ImportedAccountsService(db)
    try:
        return service.preview(
            raw=raw, filename=file.filename or "upload", mapping=mapping_dict
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/template")
async def download_template() -> Response:
    """Return a sample CSV the user can edit."""
    return Response(
        content=_TEMPLATE_CSV,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="finance-analysis-template.csv"',
        },
    )
