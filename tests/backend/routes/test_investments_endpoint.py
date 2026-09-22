"""Slash-form lock-in tests for the /api/investments endpoint.

These tests guard the fix for the CSP-blocked-307 bug. The FastAPI app is
constructed with ``redirect_slashes=False`` (see ``backend/main.py``) so the
client must send the route's exact slash form. The route is registered at
``"/"`` under the ``/api/investments`` prefix, meaning the canonical URL is
``/api/investments/`` (with trailing slash).
"""


class TestInvestmentsEndpointSlashHandling:
    """Tests guarding the trailing-slash contract of /api/investments."""

    def test_investments_without_trailing_slash_does_not_307(
        self, test_client, seed_investments
    ):
        """GET /api/investments — no slash — must not return a 307 redirect.

        With ``redirect_slashes=False`` the no-slash form is simply a 404. We
        assert it isn't a 307 because the original bug was a 307 with an
        absolute ``Location`` header pointing at the backend host, which broke
        the Vite dev proxy and tripped the browser's CSP. Returning 404 is the
        intended belt-and-braces behaviour: callers must use the canonical
        slash form (see ``frontend/src/services/api.ts``).
        """
        response = test_client.get(
            "/api/investments?include_closed=true", follow_redirects=False
        )
        assert response.status_code != 307
        assert response.status_code == 404
