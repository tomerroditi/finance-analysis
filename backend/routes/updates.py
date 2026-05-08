"""Update-availability routes.

``GET`` returns the cached probe (refreshing if stale). ``POST`` forces
a fresh probe — used by the "Check now" button on the About panel.
Both responses are intentionally identical in shape so the frontend
can render them with one component.

Excluded from the PWA service-worker runtime cache and the IndexedDB
React Query persister; the cache lives in
``~/.finance-analysis/.update_cache.json`` and we'd rather refetch from
the backend than serve a stale browser-side copy.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from backend.services.update_service import UpdateService

router = APIRouter()


class UpdateInfoModel(BaseModel):
    current: str
    latest: str | None = None
    is_outdated: bool = False
    asset_url: str | None = None
    html_url: str | None = None
    checked_at: str | None = None
    error: str | None = None


def _service() -> UpdateService:
    return UpdateService()


@router.get("/check", response_model=UpdateInfoModel)
def check_for_update() -> UpdateInfoModel:
    """Return the cached or freshly fetched update status."""
    info = _service().check(force=False)
    return UpdateInfoModel(**info.as_dict())


@router.post("/check", response_model=UpdateInfoModel)
def force_check_for_update() -> UpdateInfoModel:
    """Force a fresh GitHub probe (bypassing the 24h cache)."""
    info = _service().check(force=True)
    return UpdateInfoModel(**info.as_dict())
