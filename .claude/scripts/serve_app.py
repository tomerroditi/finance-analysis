#!/usr/bin/env python3
"""Serve the app under uvicorn, optionally on a second tailnet-only listener.

Launched by ``prod_server.py``. The main listener is what the local browser
(and any token-bearing remote client) uses. ``--tailnet-port`` opens a
second loopback listener that only ``tailscale serve`` is pointed at: the
backend believes a ``Tailscale-User-Login`` header only on that port
(``TAILNET_INGRESS_PORT``), so another local proxy in front of the main port
cannot relay a forged tailnet identity. One process serves both, so the
in-process caches stay shared.

The access log is off: the first page load of a tokenized share URL is
``GET /?apiToken=...``, and the request line would write the token to the
terminal and to whatever captures it.

Usage::

    python .claude/scripts/serve_app.py --host 127.0.0.1 --port 8080
        [--tailnet-port 8081]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    """Bind the listeners and serve until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--tailnet-port", type=int, default=None)
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    # Keep the TCP peer as the real connection: the backend tells a
    # proxy-relayed request apart from a genuinely local one by its proxy
    # headers (auth.is_proxied_request).
    config = uvicorn.Config(
        "backend.main:app",
        host=args.host,
        port=args.port,
        proxy_headers=False,
        access_log=False,
    )
    sockets = [config.bind_socket()]
    if args.tailnet_port is not None:
        # Every Config re-applies uvicorn's logging setup on construction,
        # so this one must turn the access log off too.
        tailnet = uvicorn.Config(
            "backend.main:app",
            host="127.0.0.1",
            port=args.tailnet_port,
            access_log=False,
        )
        sockets.append(tailnet.bind_socket())
    uvicorn.Server(config).run(sockets=sockets)


if __name__ == "__main__":
    main()
