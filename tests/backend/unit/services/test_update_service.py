"""
Unit tests for :class:`backend.services.update_service.UpdateService`.

Covers:
    - First call probes GitHub.
    - Within TTL, the cached result is returned without a probe.
    - ``force=True`` bypasses the cache.
    - HTTP non-200 collapses to ``error="unavailable"``.
    - Network exception collapses to ``error="unavailable"``.
    - Asset URL is OS-aware (.exe on win32, None on darwin/linux since
      we no longer ship a downloadable macOS artifact).
    - Semver compare: outdated, up-to-date, and dev (0.0.0) base case.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from backend.services import update_service
from backend.services.update_service import UpdateInfo, UpdateService


def _release_payload(
    *, tag: str = "v1.16.0", with_assets: bool = True
) -> dict[str, Any]:
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/owner/repo/releases/tag/{tag}",
        "assets": (
            [
                {
                    "name": "FinanceAnalysis.dmg",
                    "browser_download_url": "https://example/finance.dmg",
                },
                {
                    "name": "FinanceAppInstaller.exe",
                    "browser_download_url": "https://example/finance.exe",
                },
            ]
            if with_assets
            else []
        ),
    }


def _make_client(response: Any) -> httpx.Client:
    """Return a real httpx.Client whose transport is mocked."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return response if isinstance(response, httpx.Response) else response()

    return httpx.Client(transport=httpx.MockTransport(handler))


class TestUpdateServiceProbing:
    """Tests for the GitHub probe pathway."""

    def test_probe_returns_outdated_when_latest_is_higher(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Higher GitHub tag than current version sets is_outdated=True."""
        monkeypatch.setattr(update_service, "get_app_version", lambda: "1.15.1")
        client = _make_client(httpx.Response(200, json=_release_payload(tag="v1.16.0")))
        svc = UpdateService(cache_path=tmp_path / "c.json", http_client=client)

        info = svc.check()

        assert info.error is None
        assert info.current == "1.15.1"
        assert info.latest == "1.16.0"
        assert info.is_outdated is True
        assert info.html_url is not None

    def test_probe_returns_up_to_date_when_versions_match(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Equal versions do not flag is_outdated."""
        monkeypatch.setattr(update_service, "get_app_version", lambda: "1.16.0")
        client = _make_client(httpx.Response(200, json=_release_payload(tag="v1.16.0")))
        svc = UpdateService(cache_path=tmp_path / "c.json", http_client=client)

        info = svc.check()

        assert info.is_outdated is False

    def test_http_error_collapses_to_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-200 from GitHub is reported as unavailable, not raised."""
        monkeypatch.setattr(update_service, "get_app_version", lambda: "1.15.1")
        client = _make_client(httpx.Response(503, json={"message": "down"}))
        svc = UpdateService(cache_path=tmp_path / "c.json", http_client=client)

        info = svc.check()

        assert info.error == "unavailable"
        assert info.is_outdated is False
        # Failed probes must not poison the cache.
        assert not (tmp_path / "c.json").exists()

    def test_network_exception_collapses_to_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Raised httpx errors return error=unavailable instead of bubbling."""
        monkeypatch.setattr(update_service, "get_app_version", lambda: "1.15.1")

        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline")

        client = httpx.Client(transport=httpx.MockTransport(boom))
        svc = UpdateService(cache_path=tmp_path / "c.json", http_client=client)

        info = svc.check()

        assert info.error == "unavailable"


class TestUpdateServiceCaching:
    """Tests for the on-disk cache layer."""

    def test_cached_result_returned_within_ttl(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Within TTL, the second call returns cached data without probing."""
        monkeypatch.setattr(update_service, "get_app_version", lambda: "1.15.1")
        spy = MagicMock(return_value=httpx.Response(200, json=_release_payload()))
        client = _make_client(spy)
        cache_path = tmp_path / "c.json"
        svc = UpdateService(cache_path=cache_path, http_client=client)

        first = svc.check()
        second = svc.check()

        assert spy.call_count == 1  # second call hit the cache, not GitHub
        assert first.latest == second.latest

    def test_force_bypasses_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """force=True forces a fresh probe even when the cache is fresh."""
        monkeypatch.setattr(update_service, "get_app_version", lambda: "1.15.1")
        spy = MagicMock(return_value=httpx.Response(200, json=_release_payload()))
        client = _make_client(spy)
        svc = UpdateService(cache_path=tmp_path / "c.json", http_client=client)

        svc.check()
        svc.check(force=True)

        assert spy.call_count == 2

    def test_expired_cache_triggers_refresh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A cache file older than TTL is treated as missing."""
        monkeypatch.setattr(update_service, "get_app_version", lambda: "1.15.1")
        cache_path = tmp_path / "c.json"
        # Pre-populate cache and back-date it past the TTL.
        cache_path.write_text(
            json.dumps(UpdateInfo(current="1.15.1", latest="1.15.5").as_dict())
        )
        old = time.time() - 10 * 24 * 60 * 60
        import os

        os.utime(cache_path, (old, old))

        spy = MagicMock(return_value=httpx.Response(200, json=_release_payload()))
        client = _make_client(spy)
        svc = UpdateService(
            cache_path=cache_path, http_client=client, cache_ttl_seconds=24 * 3600
        )

        info = svc.check()

        assert spy.call_count == 1
        assert info.latest == "1.16.0"

    def test_cache_reevaluates_is_outdated_against_current(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the binary self-upgrades while the cache is fresh, the
        cached snapshot is reused but is_outdated is recomputed against
        the now-current version.
        """
        cache_path = tmp_path / "c.json"
        # Cache was written when current was 1.15.1 → outdated against 1.16.0.
        cache_path.write_text(
            json.dumps(
                UpdateInfo(
                    current="1.15.1",
                    latest="1.16.0",
                    is_outdated=True,
                ).as_dict()
            )
        )

        monkeypatch.setattr(update_service, "get_app_version", lambda: "1.16.0")
        svc = UpdateService(cache_path=cache_path, http_client=_make_client(MagicMock()))

        info = svc.check()

        # Process now reports 1.16.0; the cached "outdated" verdict must flip.
        assert info.current == "1.16.0"
        assert info.is_outdated is False


class TestPickAssetUrl:
    """Tests for the OS-matching asset selector.

    Only Windows ships a downloadable artifact
    (``FinanceAppInstaller.exe``). macOS and Linux fall through to
    ``None`` so the in-app update toast falls back to the release-page
    link. macOS used to ship ``FinanceAnalysis.dmg`` but Tahoe blocks
    every unsigned download path, so macOS users build from source
    instead.
    """

    @staticmethod
    def _assets() -> list[dict]:
        # Releases now ship only the .exe. We still include a .dmg here
        # to confirm the selector ignores it for non-Windows callers —
        # historical releases (v1.20 and earlier) had both assets, and
        # this guard makes sure no platform regresses to picking the
        # macOS asset for users we don't want to send there.
        return [
            {
                "name": "FinanceAnalysis.dmg",
                "browser_download_url": "https://example/finance.dmg",
            },
            {
                "name": "FinanceAppInstaller.exe",
                "browser_download_url": "https://example/installer.exe",
            },
        ]

    def test_win32_picks_exe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Windows users get the .exe."""
        monkeypatch.setattr(update_service.sys, "platform", "win32")

        assert (
            update_service._pick_asset_url(self._assets())
            == "https://example/installer.exe"
        )

    def test_darwin_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """macOS no longer ships a downloadable artifact — return None.

        Even when a legacy ``.dmg`` asset is still present on an older
        release, we don't surface it as an in-app download. Tahoe blocks
        every unsigned download path (.app/.pkg/.command all hit a
        dead-end "cannot verify" dialog), so sending users to a .dmg
        gives them a broken download experience. Falling through to
        ``None`` makes the update toast link to the release page
        instead, where the README explains the source build flow.
        """
        monkeypatch.setattr(update_service.sys, "platform", "darwin")

        assert update_service._pick_asset_url(self._assets()) is None

    def test_linux_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Linux has no shipping artifact — return None."""
        monkeypatch.setattr(update_service.sys, "platform", "linux")

        assert update_service._pick_asset_url(self._assets()) is None
