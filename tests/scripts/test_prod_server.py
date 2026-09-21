"""
Unit tests for .claude/scripts/prod_server.py — the prod supervisor behind
``./start.sh prod``.

Covered here are the decisions that are easy to get subtly wrong: what a
commit range requires of a redeploy, how the tailnet share is chosen from
``tailscale status``, when auto-pull must stand down, and when a live server
that stopped answering is restarted. Nothing starts uvicorn, runs a build or
calls Tailscale.
"""

from __future__ import annotations

import http.server
import importlib.util
import socket
import subprocess
import sys
import threading
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

    def test_version_only_manifests_cost_nothing_but_a_restart(self):
        """Verify a Commitizen bump commit is a bare restart.

        Its whole frontend diff is the version string in package.json and
        package-lock.json, which the bundle never reads.
        """
        plan = prod.plan_redeploy(
            [
                "CHANGELOG.md",
                "build/installer_script.nsi",
                "frontend/package.json",
                "frontend/package-lock.json",
                "pyproject.toml",
            ],
            version_only_paths=[
                "frontend/package.json",
                "frontend/package-lock.json",
            ],
        )
        assert plan == prod.RedeployPlan(False, False, False)

    def test_a_real_dependency_change_still_installs(self):
        """Verify subtracting version-only paths can't mask a real npm install."""
        plan = prod.plan_redeploy(
            ["frontend/package.json", "frontend/package-lock.json"],
            version_only_paths=["frontend/package.json"],
        )
        assert plan == prod.RedeployPlan(True, True, False)


class TestVersionOnlyManifests:
    """Tests for version_only_manifests() against this repository's history."""

    @staticmethod
    def _bump_commit() -> tuple[str, str]:
        """Find a real ``bump:`` commit and its parent, or skip."""
        found = prod.git(
            "log", "--format=%H", "--grep=^bump: version", "-n", "1", check=False
        )
        sha = found.stdout.strip()
        if found.returncode != 0 or not sha:
            pytest.skip("no bump commit in this checkout's history")
        parent = prod.git("rev-parse", f"{sha}^", check=False)
        if parent.returncode != 0:
            pytest.skip("bump commit has no parent in this checkout")
        return parent.stdout.strip(), sha

    def test_a_release_bump_is_recognised_as_version_only(self):
        """Verify a real bump commit's npm manifests are both version-only.

        This is the whole point: judged by path they look like a dependency
        change, so every release used to pay a full `npm ci` plus bundle
        build for two rewritten lines.
        """
        parent, sha = self._bump_commit()
        paths = prod.changed_paths_between(parent, sha)

        assert prod.version_only_manifests(parent, sha, paths) == {
            "frontend/package.json",
            "frontend/package-lock.json",
        }
        assert prod.plan_redeploy(
            paths, prod.version_only_manifests(parent, sha, paths)
        ) == prod.RedeployPlan(False, False, False)

    def test_a_range_carrying_real_frontend_work_still_builds(self):
        """Verify the merge a bump releases is unaffected by the subtraction."""
        parent, sha = self._bump_commit()
        grandparent = prod.git("rev-parse", f"{parent}^", check=False)
        if grandparent.returncode != 0:
            pytest.skip("not enough history in this checkout")
        old = grandparent.stdout.strip()
        paths = prod.changed_paths_between(old, sha)
        if not any(p.startswith("frontend/src/") for p in paths):
            pytest.skip("the released merge did not touch frontend sources")

        plan = prod.plan_redeploy(paths, prod.version_only_manifests(old, sha, paths))
        assert plan.build_frontend is True

    def test_an_unreadable_commit_is_treated_as_a_real_change(self):
        """Verify a range we can't inspect subtracts nothing."""
        assert (
            prod.version_only_manifests(
                "0" * 40, "HEAD", ["frontend/package-lock.json"]
            )
            == set()
        )

    def test_untouched_manifests_are_never_considered(self):
        """Verify only paths actually in the range can be subtracted."""
        assert prod.version_only_manifests("HEAD", "HEAD", ["backend/main.py"]) == set()


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

    def test_owner_login_is_read_from_the_user_map(self):
        """Verify the machine owner's login comes from Self.UserID -> User."""
        share, _ = prod.tailnet_share_from_status(
            {
                "BackendState": "Running",
                "Self": {"DNSName": "laptop.tail1234.ts.net.", "UserID": 42},
                "User": {"42": {"LoginName": "me@example.com"}},
                "CertDomains": ["laptop.tail1234.ts.net"],
            }
        )
        assert share.owner_login == "me@example.com"

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


class _ScriptedServer:
    """A Server stand-in whose /health answers follow a script."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.stops = 0
        self.starts = 0

    def healthy(self, timeout=None):
        return self.answers.pop(0)

    def stop(self):
        self.stops += 1

    def start(self):
        self.starts += 1
        return True


class TestSupervisorCheckHealth:
    """Tests for Supervisor.check_health() — restarting a live but deaf server."""

    @staticmethod
    def _supervisor(monkeypatch, answers):
        """Build a Supervisor around a scripted server, without touching git."""
        monkeypatch.setattr(prod, "head_commit", lambda: "abc123")
        supervisor = prod.Supervisor("127.0.0.1", 8080, 60, auto_pull=False)
        supervisor.server = _ScriptedServer(answers)
        return supervisor

    def test_isolated_misses_are_tolerated(self, monkeypatch):
        """Verify a success between misses resets the count, so no restart happens."""
        misses = prod.HEALTH_FAILURES_BEFORE_RESTART - 1
        answers = ([False] * misses + [True]) * 2
        supervisor = self._supervisor(monkeypatch, answers)
        restarts = [supervisor.check_health() for _ in answers]
        assert not any(restarts)
        assert supervisor.server.stops == 0

    def test_consecutive_misses_restart_the_server(self, monkeypatch):
        """Verify the Nth consecutive miss stops and restarts the server once."""
        n = prod.HEALTH_FAILURES_BEFORE_RESTART
        supervisor = self._supervisor(monkeypatch, [False] * n)
        restarts = [supervisor.check_health() for _ in range(n)]
        assert restarts == [False] * (n - 1) + [True]
        assert (supervisor.server.stops, supervisor.server.starts) == (1, 1)
        assert supervisor.health_failures == 0


class TestServerHealthy:
    """Tests for Server.healthy() against a real local HTTP listener."""

    def test_answers_true_while_health_responds(self):
        """Verify a 200 from /health counts as healthy."""

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200 if self.path == "/health" else 404)
                self.end_headers()

            def log_message(self, *args):
                pass

        httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            assert prod.Server("127.0.0.1", httpd.server_address[1]).healthy(timeout=5)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_answers_false_when_nothing_listens(self):
        """Verify a closed port — what a Proactor loop leaves after a failed accept — is unhealthy."""
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        assert prod.Server("127.0.0.1", port).healthy(timeout=2) is False


class TestBuildEnv:
    """Tests for build_env()."""

    BOOTLOADER = "/home/u/.vscode/extensions/ms-vscode.js-debug/src/bootloader.js"

    def test_strips_vscode_auto_attach(self):
        """Verify the js-debug bootloader and its inspector options are dropped."""
        env = prod.build_env(
            {
                "NODE_OPTIONS": f"--require {self.BOOTLOADER}",
                "VSCODE_INSPECTOR_OPTIONS": '{"inspectorIpc":"x"}',
                "PATH": "/usr/bin",
            }
        )
        assert env == {"PATH": "/usr/bin"}

    def test_keeps_other_node_options(self):
        """Verify unrelated NODE_OPTIONS flags survive the strip."""
        env = prod.build_env(
            {"NODE_OPTIONS": f"--max-old-space-size=4096 -r {self.BOOTLOADER}"}
        )
        assert env["NODE_OPTIONS"] == "--max-old-space-size=4096"

    def test_keeps_unrelated_require(self):
        """Verify a --require that is not the debugger is left alone."""
        env = prod.build_env({"NODE_OPTIONS": "--require ./instrument.js"})
        assert env["NODE_OPTIONS"] == "--require ./instrument.js"

    def test_does_not_mutate_input(self):
        """Verify the caller's environment mapping is left unchanged."""
        environ = {"NODE_OPTIONS": f"--require={self.BOOTLOADER}"}
        env = prod.build_env(environ)
        assert "NODE_OPTIONS" not in env
        assert environ == {"NODE_OPTIONS": f"--require={self.BOOTLOADER}"}
