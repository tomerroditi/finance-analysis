"""Tests for the ``uvicorn --reload`` event loop factory."""

import asyncio
import errno
import socket
import sys
from unittest.mock import patch

import pytest
import uvicorn

from backend.utils import event_loop
from backend.utils.event_loop import (
    ResilientSelectSelector,
    reload_loop_factory,
)

_LOOP_SPEC = "backend.utils.event_loop:reload_loop_factory"


class TestReloadLoopFactory:
    """The factory uvicorn resolves from ``--loop``."""

    def test_uvicorn_resolves_the_loop_spec(self):
        """``uvicorn.Config(loop=...)`` imports the factory the launch scripts name."""
        config = uvicorn.Config("backend.main:app", reload=True, loop=_LOOP_SPEC)
        assert config.get_loop_factory() is reload_loop_factory

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-only loop choice")
    def test_windows_gets_a_selector_loop_over_the_resilient_selector(self):
        """On Windows the worker runs a SelectorEventLoop (a Proactor cannot re-accept the reloader's shared socket)."""
        loop = reload_loop_factory()
        try:
            assert isinstance(loop, asyncio.SelectorEventLoop)
            assert isinstance(loop._selector, ResilientSelectSelector)
        finally:
            loop.close()

    def test_loop_serves_a_connection(self):
        """A loop from the factory can accept and answer a TCP connection."""

        async def exchange() -> bytes:
            async def handle(reader, writer):
                writer.write(await reader.readexactly(4))
                await writer.drain()
                writer.close()

            server = await asyncio.start_server(handle, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"ping")
            reply = await reader.readexactly(4)
            writer.close()
            server.close()
            await server.wait_closed()
            return reply

        assert asyncio.run(exchange(), loop_factory=reload_loop_factory) == b"ping"


class TestResilientSelectSelector:
    """``select()`` failures that used to kill the dev worker."""

    def test_no_buffer_space_backs_off_instead_of_raising(self):
        """WinError 10055 / ENOBUFS yields "nothing ready" and a warning, not an exception."""
        selector = ResilientSelectSelector()
        a, b = socket.socketpair()
        try:
            selector.register(a, event_loop.selectors.EVENT_READ)
            no_buffers = OSError(errno.ENOBUFS, "no buffer space")
            with patch.object(event_loop.select, "select", side_effect=no_buffers), \
                    patch.object(event_loop.time, "sleep") as sleep, \
                    patch.object(event_loop.logger, "warning") as warning:
                assert selector.select(0) == []
                assert selector.select(0) == []
            sleep.assert_called()
            assert warning.call_count == 1
        finally:
            selector.close()
            a.close()
            b.close()

    def test_other_os_errors_still_raise(self):
        """Only buffer exhaustion is swallowed; any other select() error surfaces."""
        selector = ResilientSelectSelector()
        a, b = socket.socketpair()
        try:
            selector.register(a, event_loop.selectors.EVENT_READ)
            with patch.object(
                event_loop.select, "select", side_effect=OSError(errno.EBADF, "bad fd")
            ), pytest.raises(OSError):
                selector.select(0)
        finally:
            selector.close()
            a.close()
            b.close()

    def test_more_descriptors_than_fd_setsize_are_polled_in_chunks(self):
        """Above the 512-descriptor select() cap, every call stays under it and readiness is still found."""
        selector = ResilientSelectSelector()
        fds = list(range(1000, 1000 + event_loop._SELECT_FD_LIMIT * 2 + 10))
        ready_fd = fds[-1]
        calls = []

        def fake_select(r, w, x, timeout):
            calls.append((len(r), len(w), timeout))
            return [fd for fd in r if fd == ready_fd], [], []

        with patch.object(event_loop.select, "select", side_effect=fake_select):
            ready_r, ready_w, _ = selector._select(fds, [], [], 1.0)

        assert ready_r == [ready_fd]
        assert ready_w == []
        assert len(calls) == 3
        assert all(n_r <= event_loop._SELECT_FD_LIMIT for n_r, _, _ in calls)
        assert all(timeout == 0 for _, _, timeout in calls)

    def test_chunked_poll_honours_the_timeout(self):
        """With nothing ready, chunked polling returns empty once the timeout lapses."""
        selector = ResilientSelectSelector()
        fds = list(range(1000, 1000 + event_loop._SELECT_FD_LIMIT + 1))
        with patch.object(event_loop.select, "select", return_value=([], [], [])):
            assert selector._select(fds, [], [], 0.02) == ([], [], [])
