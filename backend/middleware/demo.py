"""Per-request Demo Mode resolution."""

from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import RequestResponseEndpoint

from backend import demo_sessions
from backend.config import AppConfig

# Values of X-FAD-Demo that select the demo database. Anything else — an
# absent header, "0", or a malformed value — resolves to real mode.
_DEMO_HEADER_TRUTHY = frozenset({"1", "true"})


async def resolve_demo_mode(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    """Bind the request's demo-mode flag from the ``X-FAD-Demo`` header.

    Demo Mode is per-client: the flag lives in a context variable rather
    than on a process-global singleton, so two clients on one backend can
    read different databases concurrently. The header is the client's whole
    declaration — the backend stores nothing per client.

    When per-visitor sandboxes are enabled (``FAD_DEMO_SESSIONS=1``, the
    Vercel deployment), a demo request that also carries a well-formed
    ``X-FAD-Demo-Session`` id is served from that visitor's private copy of
    the demo database — see :mod:`backend.demo_sessions`.

    Parameters
    ----------
    request : Request
        Incoming request.
    call_next : RequestResponseEndpoint
        The rest of the middleware stack.

    Returns
    -------
    Response
        The downstream response, served in the resolved mode.
    """
    config = AppConfig()
    if AppConfig._forced_mode is not None:
        enabled = AppConfig._forced_mode
        token = None
    else:
        header = request.headers.get("x-fad-demo", "")
        enabled = header.strip().lower() in _DEMO_HEADER_TRUTHY
        # ensure_dir=False: this middleware only binds the context-local flag
        # for the request's duration and never itself touches the filesystem,
        # so the os.makedirs set_demo_mode() otherwise performs on every enable
        # would be a blocking syscall on the event loop for every demo-mode
        # request. The demo user directory is guaranteed to already exist by
        # the time any client can be in demo mode — the demo DB build
        # (backend/demo_setup.py, via routes/testing.py and index.py) creates
        # it via its own set_demo_mode(True) call, which keeps the default
        # ensure_dir=True.
        token = config.set_demo_mode(enabled, ensure_dir=False)

    session_id = None
    if enabled and demo_sessions.sessions_enabled():
        session_id = demo_sessions.parse_session_id(
            request.headers.get(demo_sessions.SESSION_HEADER)
        )
    try:
        if session_id is None:
            return await call_next(request)
        return await demo_sessions.serve_in_session(request, call_next, session_id)
    finally:
        # Requests are served from a shared threadpool; without the reset a
        # worker would carry this mode into the next request it picks up.
        if token is not None:
            config.reset_demo_mode(token)
