"""
Unit tests for .claude/scripts/e2e_parallel_isolated.py — the isolated
parallel e2e orchestrator.

Scope is deliberately the *port ownership* logic, which is what made
concurrent runs dangerous: with fixed ports, a second worktree's Vite could
not bind :5273, silently moved to the next free port, and its shards still
pointed `BASE_URL` at :5273 — so they drove the neighbour's app and failed on
locators that were perfectly correct.

Nothing here starts a server or a browser; the real end-to-end behaviour is
covered by actually running the suite.
"""

from __future__ import annotations

import importlib.util
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Not an importable package (`.claude` is not a valid identifier), so load it
# from its path the way tests/build/test_app_entry.py loads build/app_entry.py.
_SPEC = importlib.util.spec_from_file_location(
    "e2e_parallel_isolated", ROOT / ".claude" / "scripts" / "e2e_parallel_isolated.py"
)
runner = importlib.util.module_from_spec(_SPEC)
sys.modules["e2e_parallel_isolated"] = runner
_SPEC.loader.exec_module(runner)


@pytest.fixture
def bound_port():
    """Hold a real listening socket, yielding the port it occupies."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    yield sock.getsockname()[1]
    sock.close()


class TestPortIsFree:
    """The bind-based freeness probe."""

    def test_occupied_port_is_not_free(self, bound_port):
        """A port with a live listener cannot be bound, so it is not free."""
        assert runner.port_is_free(bound_port) is False

    def test_released_port_becomes_free(self):
        """A port is free once nothing holds it.

        The socket is never listened on, so closing it leaves no TIME_WAIT —
        the probe should report the port free immediately.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()
        assert runner.port_is_free(port) is True

    def test_detects_a_bound_but_unlistening_socket(self):
        """Bind-not-listen still owns the port; a connect probe would miss it.

        This is the case that makes a bind test worth the extra syscall: the
        server we are about to start would fail on exactly this port, but
        nothing accepts connections on it yet.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        try:
            assert runner.port_is_listening(port) is False
            assert runner.port_is_free(port) is False
        finally:
            sock.close()


class TestPortAllocator:
    """Allocation prefers `base + index` but never insists on it."""

    def test_prefers_base_plus_index(self, monkeypatch):
        """With everything free, shards get the canonical consecutive ports.

        Freeness is stubbed rather than probed: whether :8100 happens to be
        free on the machine running the tests is not what this asserts, and a
        TIME_WAIT socket from a real run must not turn it red.
        """
        monkeypatch.setattr(runner, "port_is_free", lambda port: True)
        alloc = runner.PortAllocator(8100, 5273)
        assert [alloc.take(8100, i) for i in range(3)] == [8100, 8101, 8102]

    def test_skips_an_occupied_port(self, monkeypatch):
        """A held port is stepped over rather than fought for."""
        monkeypatch.setattr(runner, "port_is_free", lambda port: port != 5273)
        alloc = runner.PortAllocator(8100, 5273)
        assert alloc.take(5273, 0) == 5274

    def test_never_hands_out_the_same_port_twice(self, monkeypatch):
        """Two shards whose preferred ports collide still get distinct ones."""
        monkeypatch.setattr(runner, "port_is_free", lambda port: True)
        alloc = runner.PortAllocator(8100, 5273)
        assert alloc.take(5273, 0) == 5273
        # Same preferred port requested again: the allocator's own bookkeeping
        # must exclude it even though the OS still reports it free (nothing has
        # bound it yet — the server for shard 0 has not started).
        assert alloc.take(5273, 0) == 5274

    def test_released_ports_are_reusable(self, monkeypatch):
        """A retry that gives its ports back can be handed them again."""
        monkeypatch.setattr(runner, "port_is_free", lambda port: True)
        alloc = runner.PortAllocator(8100, 5273)
        port = alloc.take(8100, 0)
        alloc.release(port)
        assert alloc.take(8100, 0) == port

    def test_exhausting_the_span_raises(self, monkeypatch):
        """When nothing in range is free, say so instead of hanging."""
        monkeypatch.setattr(runner, "port_is_free", lambda port: False)
        alloc = runner.PortAllocator(8100, 5273, span=5)
        with pytest.raises(RuntimeError, match="no free port in 8100-8104"):
            alloc.take(8100, 0)


class TestPairPortPropagation:
    """Allocated ports must reach the URLs the shard is pinned to."""

    def test_urls_follow_the_allocated_ports(self, monkeypatch):
        """BASE_URL and E2E_API_BASE track allocation, not the preferred base.

        This is the actual regression: the old runner hard-coded the ports into
        both the servers *and* the URLs, so when Vite moved, the URLs did not.
        """
        monkeypatch.setattr(runner, "port_is_free", lambda port: port not in (8100, 5273))
        monkeypatch.setattr(runner, "describe_port_holder", lambda port: "a test double")
        alloc = runner.PortAllocator(8100, 5273)
        pair = runner.Pair(0)
        try:
            pair.assign_ports(alloc)
            assert (pair.backend_port, pair.frontend_port) == (8101, 5274)
            assert pair.base_url == "http://localhost:5274"
            assert pair.api_base == "http://localhost:8101/api"
        finally:
            import shutil

            shutil.rmtree(pair.user_dir, ignore_errors=True)


class TestEnvPortBase:
    """Env overrides, and the bad values they must not honour."""

    def test_absent_env_uses_the_default(self, monkeypatch):
        """No override means the built-in base."""
        monkeypatch.delenv("E2E_BACKEND_PORT_BASE", raising=False)
        assert runner.env_port_base("E2E_BACKEND_PORT_BASE", 8100) == 8100

    def test_valid_override_wins(self, monkeypatch):
        """A sane port is taken as-is."""
        monkeypatch.setenv("E2E_BACKEND_PORT_BASE", "8400")
        assert runner.env_port_base("E2E_BACKEND_PORT_BASE", 8100) == 8400

    @pytest.mark.parametrize("bad", ["", "abc", "80", "99999", "-1"])
    def test_unusable_values_fall_back(self, monkeypatch, bad):
        """Garbage or out-of-range values must not silently pick a bad port."""
        monkeypatch.setenv("E2E_BACKEND_PORT_BASE", bad)
        assert runner.env_port_base("E2E_BACKEND_PORT_BASE", 8100) == 8100


class TestReadLog:
    """Log reading must survive Playwright's non-UTF-8 output."""

    def test_invalid_utf8_does_not_raise(self, tmp_path):
        """A stray 0x94 byte used to abort the whole summary loop."""
        log = tmp_path / "shard.log"
        log.write_bytes(b"Running 1 test\n\x94garbled\n  1 passed (2.0s)\n")
        with pytest.raises(UnicodeDecodeError):
            log.read_text()
        assert "1 passed (2.0s)" in runner.read_log(log)

    def test_missing_file_reads_as_empty(self, tmp_path):
        """A shard that never wrote a log should not crash the summary."""
        assert runner.read_log(tmp_path / "absent.log") == ""


class TestLogDirIsolation:
    """Logs and reports must not collide between checkouts."""

    def test_log_dir_is_scoped_to_this_checkout(self):
        """A flat $TMPDIR name would let two worktrees clobber each other.

        The JSON reports matter most: `collect_timings` reads them back and
        writes the result into the committed timings file, so a shared path
        would fold a neighbouring checkout's numbers into this repo.
        """
        assert runner.LOG_DIR.name.startswith("e2e-isolated-")
        assert runner.REPO_ROOT.name in runner.LOG_DIR.name
