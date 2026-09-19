"""
Unit tests for .claude/scripts/prod_server.py — the prod supervisor behind
``./start.sh prod``.

Covered here are the decisions that are easy to get subtly wrong: what a
commit range requires of a redeploy, how the tailnet share is chosen from
``tailscale status``, and when auto-pull must stand down. Nothing starts a
server, runs a build or calls Tailscale.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "prod_server", ROOT / ".claude" / "scripts" / "prod_server.py"
)
prod = importlib.util.module_from_spec(_SPEC)
sys.modules["prod_server"] = prod
_SPEC.loader.exec_module(prod)


class TestPlanRedeploy:
    """Tests for plan_redeploy()."""

    def test_backend_only_change_skips_frontend_and_deps(self):
        """Verify a backend-only commit just restarts the server."""
        plan = prod.plan_redeploy(["backend/main.py", "scraper/base.py"])
        assert plan == prod.RedeployPlan(False, False, False)

    def test_frontend_source_change_rebuilds_without_npm_ci(self):
        """Verify a frontend source change rebuilds but keeps node_modules."""
        plan = prod.plan_redeploy(["frontend/src/App.tsx"])
        assert plan.build_frontend is True
        assert plan.install_frontend_deps is False

    def test_lockfile_changes_trigger_dependency_installs(self):
        """Verify both lock files trigger their installers."""
        plan = prod.plan_redeploy(["frontend/package-lock.json", "poetry.lock"])
        assert plan == prod.RedeployPlan(True, True, True)

    def test_nested_poetry_lock_is_not_the_root_lock(self):
        """Verify only the repo-root poetry.lock re-syncs the venv."""
        assert prod.plan_redeploy(["tools/poetry.lock"]).sync_python_deps is False


class TestChangedPathsBetween:
    """Tests for changed_paths_between()."""

    def test_unknown_commit_falls_back_to_a_full_redeploy(self, monkeypatch):
        """Verify a failed diff (e.g. history rewritten) plans every step."""
        failed = subprocess.CompletedProcess([], 128, stdout="", stderr="bad revision")
        monkeypatch.setattr(prod, "git", lambda *a, **k: failed)
        plan = prod.plan_redeploy(prod.changed_paths_between("aaa", "bbb"))
        assert plan == prod.RedeployPlan(True, True, True)


class TestTailnetShareFromStatus:
    """Tests for tailnet_share_from_status()."""

    RUNNING: ClassVar[dict] = {
        "BackendState": "Running",
        "Self": {"DNSName": "laptop.tail1234.ts.net."},
    }

    def test_https_when_certificates_are_enabled(self):
        """Verify a tailnet with cert domains is shared over HTTPS."""
        share, note = prod.tailnet_share_from_status(
            {**self.RUNNING, "CertDomains": ["laptop.tail1234.ts.net"]}
        )
        assert share == prod.TailnetShare(
            "laptop.tail1234.ts.net", "https://laptop.tail1234.ts.net", "--https=443"
        )
        assert note == ""

    def test_http_fallback_without_certificates(self):
        """Verify a tailnet without certs falls back to HTTP and says why."""
        share, note = prod.tailnet_share_from_status(
            {**self.RUNNING, "CertDomains": None}
        )
        assert share.url == "http://laptop.tail1234.ts.net"
        assert share.serve_flag == "--http=80"
        assert "HTTPS Certificates" in note

    @pytest.mark.parametrize(
        "status",
        [
            {},
            {"BackendState": "Stopped", "Self": {"DNSName": "laptop.tail1234.ts.net."}},
            {"BackendState": "Running", "Self": {"DNSName": ""}},
        ],
    )
    def test_no_share_when_disconnected_or_nameless(self, status):
        """Verify nothing is shared when Tailscale can't give a tailnet URL."""
        share, note = prod.tailnet_share_from_status(status)
        assert share is None
        assert note


class TestPullLatest:
    """Tests for pull_latest()'s guards."""

    @staticmethod
    def _fake_git(responses):
        """Build a git() stub answering by subcommand, recording the calls."""
        calls = []

        def fake(*args, check=True):
            calls.append(args[0])
            code, out = responses.get(args[0], (0, ""))
            return subprocess.CompletedProcess(args, code, stdout=out, stderr="")

        return fake, calls

    def test_no_upstream_skips_without_fetching(self, monkeypatch):
        """Verify a branch with no upstream is never fetched."""
        fake, calls = self._fake_git({"rev-parse": (128, "")})
        monkeypatch.setattr(prod, "git", fake)
        assert "no upstream" in prod.pull_latest()
        assert "fetch" not in calls

    def test_dirty_checkout_is_left_alone(self, monkeypatch):
        """Verify uncommitted tracked changes block the pull."""
        fake, calls = self._fake_git({"status": (0, " M backend/main.py")})
        monkeypatch.setattr(prod, "git", fake)
        assert "uncommitted" in prod.pull_latest()
        assert "merge" not in calls

    def test_diverged_branch_reports_instead_of_merging(self, monkeypatch):
        """Verify a non-fast-forward is reported, never forced."""
        fake, _ = self._fake_git({"merge": (128, "")})
        monkeypatch.setattr(prod, "git", fake)
        assert "diverged" in prod.pull_latest()

    def test_clean_fast_forward_succeeds(self, monkeypatch):
        """Verify a clean checkout with an upstream fetches and fast-forwards."""
        fake, calls = self._fake_git({})
        monkeypatch.setattr(prod, "git", fake)
        assert prod.pull_latest() is None
        assert calls[-2:] == ["fetch", "merge"]


class TestServeConfigActive:
    """Tests for serve_config_active()."""

    def test_empty_config_is_free(self):
        """Verify an empty JSON config (or no output) means no share exists."""
        assert prod.serve_config_active("{}") is False
        assert prod.serve_config_active("") is False

    def test_foreground_share_counts_as_active(self):
        """Verify another process's foreground share is detected.

        The plain-text status prints "No serve config" for it, which is why
        the JSON form is read.
        """
        raw = '{"Foreground": {"abc": {"TCP": {"80": {"HTTP": true}}}}}'
        assert prod.serve_config_active(raw) is True

    def test_unparseable_output_is_treated_as_active(self):
        """Verify an unexpected answer leaves any existing share alone."""
        assert prod.serve_config_active("permission denied") is True
