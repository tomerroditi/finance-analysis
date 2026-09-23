"""HTTP middleware stack for the API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.middleware import security
from backend.middleware.demo import resolve_demo_mode

# Registration order, innermost first. Starlette makes the last-registered
# middleware the outermost, so a request passes through these bottom-up:
# security headers, the CSRF check, the remote token, the Host allowlist and
# the body cap all run before a Demo Mode is resolved — a request any of them
# rejects never binds a mode — and CORS and GZip sit closest to the routes.
_HTTP_MIDDLEWARE = (
    resolve_demo_mode,
    security.limit_request_size,
    security.enforce_host_allowlist,
    security.require_token_for_remote_clients,
    security.enforce_same_origin_for_writes,
    security.add_security_headers,
)


def register_middleware(app: FastAPI) -> None:
    """Install the API's middleware stack on ``app``.

    Parameters
    ----------
    app : FastAPI
        Application to install the middleware on.
    """
    # Compress responses. The dashboard alone pulls ~1.3 MB of JSON and the
    # production build serves a similar weight of JS/CSS from /assets — on a
    # phone that is seconds of transfer before any rendering starts. JSON of
    # this shape compresses ~11x (the transactions response measured
    # 1233 KB -> 111 KB). Registered first, so it is the innermost layer and
    # compresses what the routes and static files return; the outer layers
    # only add headers or short-circuit with tiny error bodies. 500 bytes is
    # the usual floor below which framing costs more than it saves.
    app.add_middleware(GZipMiddleware, minimum_size=500)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=security.CORS_ORIGINS,
        allow_credentials=security.CORS_ALLOW_CREDENTIALS,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-FAD-Demo",
            "X-FAD-Demo-Session",
        ],
    )
    for dispatch in _HTTP_MIDDLEWARE:
        app.middleware("http")(dispatch)
