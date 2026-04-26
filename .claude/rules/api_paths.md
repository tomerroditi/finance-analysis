# API Path Conventions — Trailing Slashes & Vite Proxy

How frontend and backend route paths must agree to avoid CSP-blocked redirects
in dev. Read this before adding a route or an API client method.

## The bug this prevents

In dev, the browser hits `http://localhost:5173/api/foo`. Vite proxies that
to `http://127.0.0.1:8000/api/foo`. If FastAPI registered the route as
`@router.get("/")` (trailing slash) but the client called `/foo` (no slash),
FastAPI returns a `307` redirect with `Location: http://localhost:8000/api/foo/`
**absolute URL pointing at the backend host**. The browser tries to follow it
and the strict CSP `connect-src 'self' ws: wss:` (in `frontend/index.html`)
blocks it because `localhost:8000` ≠ `'self'` (`localhost:5173`).

The whole page silently breaks. Console shows `Refused to connect to ...`.

This bit the Investments page in production. Don't let it bite the next page.

## Rule 1 — Disable redirect_slashes on the FastAPI app

`backend/main.py` constructs the FastAPI app with `redirect_slashes=False`.
Every route must match exactly — no auto-redirect to add or strip a slash.
Don't change this. If you do, every route needs to be audited for client-side
trailing-slash agreement.

## Rule 2 — Frontend `services/api.ts` paths must match backend exactly

`frontend/src/services/api.ts` is the only place that talks to the backend.
For every `api.get/post/put/delete` call, the path string must match the
FastAPI route definition character-for-character — including the trailing
slash, or its absence.

```ts
// backend route: @router.get("/")            → "/investments/"
api.get("/investments/", { params: { include_closed } })

// backend route: @router.get("/{id}")        → "/investments/123"
api.get(`/investments/${id}`)

// backend route: @router.get("/portfolio-analysis")
api.get("/investments/portfolio-analysis")
```

When adding a new endpoint, look at how the route is registered in
`backend/routes/<resource>.py`. Mirror it exactly in `services/api.ts`.

## Rule 3 — Test both paths if you must support both

If for some reason a route must accept both `/foo` and `/foo/` (e.g.
backwards compat with an external caller), register both explicitly:

```python
@router.get("")
@router.get("/")
def list_things(...): ...
```

Don't rely on `redirect_slashes`. Add a route test that exercises both paths.

## Rule 4 — When you change a route, audit the client

If you rename or restructure a backend route, grep `services/api.ts` for the
old path AND the new path. Both forms (with and without trailing slash) must
be checked. Run the frontend in dev and click through the relevant page —
silent CSP blocks don't surface as test failures.

## Quick audit command

After any backend route change:

```bash
# Find every API call in the client.
grep -rEn 'api\.(get|post|put|delete|patch)\("' frontend/src/services/api.ts

# Hit each one through the backend and confirm no 307.
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" \
  http://localhost:8000/api/<path>
```

Any 307 means the client path doesn't match the route — fix the client.
