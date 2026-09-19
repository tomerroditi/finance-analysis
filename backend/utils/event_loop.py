"""Event loop factory for the dev server (``uvicorn --reload``).

Passed as ``--loop backend.utils.event_loop:reload_loop_factory``. Under
``--reload`` uvicorn runs the server on a ``SelectorEventLoop`` on Windows,
and it has to: the reloader owns the listening socket and hands it to every
worker it spawns, and a ``ProactorEventLoop`` binds that socket to its I/O
completion port — which Windows allows once per socket, so the worker spawned
by the first reload dies with ``OSError: [WinError 87]`` on accept and never
serves again.

``select()`` itself is the weak point, though. It raises, and the exception
unwinds straight out of the event loop and kills the worker, in two ways:

* ``OSError: [WinError 10055]`` (no buffer space) when the machine is briefly
  short of socket buffers — seen with seven scrapes (each a browser) running
  while the frontend polled their status;
* ``ValueError: too many file descriptors in select()`` once more than 512
  sockets are open, the Windows ``FD_SETSIZE``.

:class:`ResilientSelectSelector` rides out both: it backs off on buffer
exhaustion instead of raising, and polls in chunks above ``FD_SETSIZE``.
``./start.sh prod`` and the packaged app run without ``--reload`` and already get a
``ProactorEventLoop`` from uvicorn, so they do not use this factory.
"""

import asyncio
import errno
import logging
import select
import selectors
import sys
import time

from uvicorn.loops.auto import auto_loop_factory

logger = logging.getLogger(__name__)

# Windows builds CPython with FD_SETSIZE = 512 and select() rejects any list
# longer than that.
_SELECT_FD_LIMIT = 512
_WSAENOBUFS = 10055
_NO_BUFFER_BACKOFF_SECONDS = 0.05
_CHUNKED_POLL_INTERVAL_SECONDS = 0.01
_WARNING_INTERVAL_SECONDS = 5.0


def _is_no_buffer_space(exc: OSError) -> bool:
    """Whether ``exc`` is the transient "no buffer space" socket error.

    Parameters
    ----------
    exc : OSError
        The error ``select()`` raised.

    Returns
    -------
    bool
        True for ``WSAENOBUFS`` / ``ENOBUFS``.
    """
    return exc.errno == errno.ENOBUFS or getattr(exc, "winerror", None) == _WSAENOBUFS


class ResilientSelectSelector(selectors.SelectSelector):
    """``select()`` selector that survives socket-buffer exhaustion and >512 fds."""

    def __init__(self) -> None:
        super().__init__()
        self._last_warning = float("-inf")

    def _select(self, r, w, _, timeout=None):
        """Wait for readiness like ``select.select``, without killing the loop.

        Parameters
        ----------
        r, w : Iterable[int]
            File descriptors watched for reading / writing.
        _ : Iterable[int]
            Unused, kept for the ``SelectSelector._select`` signature.
        timeout : float or None
            Seconds to wait; ``None`` waits indefinitely.

        Returns
        -------
        tuple[list[int], list[int], list[int]]
            Ready readers, ready writers (including error'd connects, which
            Windows reports in the exceptional set) and an empty list.
        """
        r, w = list(r), list(w)
        try:
            if len(r) <= _SELECT_FD_LIMIT and len(w) <= _SELECT_FD_LIMIT:
                return self._select_once(r, w, timeout)
            return self._select_chunked(r, w, timeout)
        except OSError as exc:
            if not _is_no_buffer_space(exc):
                raise
            now = time.monotonic()
            if now - self._last_warning >= _WARNING_INTERVAL_SECONDS:
                self._last_warning = now
                logger.warning(
                    "select() ran out of socket buffer space with %d sockets "
                    "open; backing off instead of stopping the server",
                    len(set(r) | set(w)),
                )
            time.sleep(_NO_BUFFER_BACKOFF_SECONDS)
            return [], [], []

    @staticmethod
    def _select_once(r: list, w: list, timeout):
        """One ``select.select`` call, folding the exceptional set into writers."""
        ready_r, ready_w, ready_x = select.select(r, w, w, timeout)
        return ready_r, ready_w + ready_x, []

    def _select_chunked(self, r: list, w: list, timeout):
        """Poll descriptors in ``FD_SETSIZE`` chunks until one is ready or time runs out."""
        deadline = None if timeout is None else time.monotonic() + timeout
        step = _SELECT_FD_LIMIT
        while True:
            ready_r: list = []
            ready_w: list = []
            for start in range(0, max(len(r), len(w)), step):
                cr, cw, _ = self._select_once(r[start:start + step], w[start:start + step], 0)
                ready_r += cr
                ready_w += cw
            if ready_r or ready_w:
                return ready_r, ready_w, []
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return [], [], []
                time.sleep(min(_CHUNKED_POLL_INTERVAL_SECONDS, remaining))
            else:
                time.sleep(_CHUNKED_POLL_INTERVAL_SECONDS)


def reload_loop_factory() -> asyncio.AbstractEventLoop:
    """Create the event loop for a ``uvicorn --reload`` worker.

    Returns
    -------
    asyncio.AbstractEventLoop
        On Windows, a ``SelectorEventLoop`` over :class:`ResilientSelectSelector`;
        elsewhere whatever uvicorn's ``auto`` loop picks (``uvloop`` when
        installed), since epoll/kqueue have neither failure mode.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(ResilientSelectSelector())
    return auto_loop_factory(use_subprocess=True)()
