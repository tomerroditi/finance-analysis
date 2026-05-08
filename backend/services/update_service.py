"""Update-availability check against GitHub Releases.

Periodically asks the GitHub Releases API whether a newer Finance
Analysis version has been published, caches the answer to disk so we
don't hammer the unauthenticated GitHub API (60 requests / hour / IP),
and returns a structured ``UpdateInfo`` the frontend can render as a
toast or an "About" panel.

Design choices:

- **Cache lives on the backend, not in the browser.** The PWA persists
  React Query results to IndexedDB; if the cache lived there each
  user-agent reload would re-hit GitHub. A backend file cache is
  shared by all open windows on the machine.
- **Failures never raise.** Any error (offline, 5xx, rate-limited,
  malformed JSON) collapses to ``UpdateInfo(error="unavailable")`` so
  the frontend can fall back to "couldn't check" copy without trying
  to interpret HTTP status codes.
- **Asset selection is OS-aware.** macOS users get a direct ``.dmg``
  link, Windows users get a direct ``.exe`` link. Linux falls through
  to ``html_url`` since we don't ship a Linux artifact.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from backend.config import AppConfig
from backend.utils.version import get_app_version

logger = logging.getLogger(__name__)

GITHUB_RELEASES_URL = (
    "https://api.github.com/repos/tomerroditi/finance-analysis/releases/latest"
)
RELEASES_HTML_URL = "https://github.com/tomerroditi/finance-analysis/releases"
CACHE_TTL_SECONDS = 24 * 60 * 60
HTTP_TIMEOUT_SECONDS = 5.0


@dataclass
class UpdateInfo:
    """Result of an update check.

    ``error`` is set to ``"unavailable"`` when the check failed
    (offline, GitHub 5xx, rate-limited). The other fields are
    best-effort — ``current`` is always populated, the rest may be
    ``None`` on error.
    """

    current: str
    latest: Optional[str] = None
    is_outdated: bool = False
    asset_url: Optional[str] = None
    html_url: Optional[str] = None
    checked_at: Optional[str] = None
    error: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


def _cache_path() -> Path:
    """Return the on-disk cache location.

    Always uses the *base* user dir (not the demo one), so a single
    cache is shared between production and demo modes — the available
    update is a property of the binary, not of the active database.
    """
    base = Path(AppConfig()._base_user_dir)  # noqa: SLF001
    base.mkdir(parents=True, exist_ok=True)
    return base / ".update_cache.json"


def _parse_semver(version: str) -> tuple[int, ...]:
    """Lenient semver tuple parse for comparison.

    Accepts a leading ``v`` and trailing pre-release/build segments. We
    only need to decide ``current < latest``, so a tuple compare on the
    first three numeric segments is enough; anything that doesn't parse
    is treated as ``(0, 0, 0)`` so a malformed tag never fakes an
    update.
    """
    cleaned = version.lstrip("vV").split("-", 1)[0].split("+", 1)[0]
    parts = cleaned.split(".")
    out: list[int] = []
    for p in parts[:3]:
        try:
            out.append(int(p))
        except ValueError:
            return (0, 0, 0)
    while len(out) < 3:
        out.append(0)
    return tuple(out)


def _pick_asset_url(assets: list[dict]) -> Optional[str]:
    """Pick the OS-matching release asset download URL.

    macOS releases ship a single arm64 ``FinanceAnalysis.dmg`` (Apple
    Silicon only — Intel Macs have been off Apple's product line since
    2022 and GitHub's ``macos-13`` Intel runner pool was too scarce to
    rely on). Windows ships ``FinanceAppInstaller.exe``. Linux has no
    shipping artifact.

    We don't inspect ``content_type`` because GitHub returns
    ``application/octet-stream`` for all binaries.
    """
    suffix_by_platform = {
        "darwin": ".dmg",
        "win32": ".exe",
    }
    suffix = suffix_by_platform.get(sys.platform)
    if suffix is None:
        return None
    for asset in assets:
        if asset.get("name", "").lower().endswith(suffix):
            return asset.get("browser_download_url")
    return None


class UpdateService:
    """Coordinates GitHub probing + on-disk caching of the result."""

    def __init__(
        self,
        *,
        cache_path: Optional[Path] = None,
        cache_ttl_seconds: int = CACHE_TTL_SECONDS,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._cache_path = cache_path or _cache_path()
        self._cache_ttl = cache_ttl_seconds
        self._http = http_client

    def check(self, *, force: bool = False) -> UpdateInfo:
        """Return cached result, or refresh when stale / forced.

        Always returns a populated :class:`UpdateInfo`. Network errors
        propagate as ``error="unavailable"``; the caller (route or
        frontend) treats that as "no toast, show muted copy on the
        About panel".
        """
        current = get_app_version()
        if not force:
            cached = self._read_cache()
            if cached is not None:
                # Re-evaluate is_outdated against the *current* version —
                # the cached snapshot might be from before a self-upgrade.
                cached.current = current
                cached.is_outdated = self._is_outdated(current, cached.latest)
                return cached

        info = self._probe_github(current=current)
        # Only persist successful probes; cached errors would suppress
        # retries during the TTL window for no reason.
        if info.error is None:
            self._write_cache(info)
        return info

    def _is_outdated(self, current: str, latest: Optional[str]) -> bool:
        if not latest:
            return False
        return _parse_semver(current) < _parse_semver(latest)

    def _probe_github(self, *, current: str) -> UpdateInfo:
        client = self._http or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
        owns_client = self._http is None
        try:
            resp = client.get(
                GITHUB_RELEASES_URL,
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code != 200:
                logger.info("GitHub releases probe returned %s", resp.status_code)
                return UpdateInfo(current=current, error="unavailable")
            payload = resp.json()
            tag = payload.get("tag_name") or ""
            latest = tag.lstrip("vV") or None
            asset_url = _pick_asset_url(payload.get("assets") or [])
            return UpdateInfo(
                current=current,
                latest=latest,
                is_outdated=self._is_outdated(current, latest),
                asset_url=asset_url,
                html_url=payload.get("html_url") or RELEASES_HTML_URL,
                checked_at=datetime.now(tz=timezone.utc).isoformat(),
            )
        except Exception as exc:
            logger.info("GitHub releases probe failed: %s", exc)
            return UpdateInfo(current=current, error="unavailable")
        finally:
            if owns_client:
                client.close()

    def _read_cache(self) -> Optional[UpdateInfo]:
        try:
            stat = self._cache_path.stat()
        except FileNotFoundError:
            return None
        if (time.time() - stat.st_mtime) > self._cache_ttl:
            return None
        try:
            data = json.loads(self._cache_path.read_text())
            return UpdateInfo(**data)
        except Exception as exc:
            logger.debug("Couldn't read update cache: %s", exc)
            return None

    def _write_cache(self, info: UpdateInfo) -> None:
        try:
            self._cache_path.write_text(json.dumps(info.as_dict()))
        except Exception as exc:
            logger.debug("Couldn't persist update cache: %s", exc)
