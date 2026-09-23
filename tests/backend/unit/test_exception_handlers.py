"""Tests for the single ``AppException`` handler in ``backend.exception_handlers``."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.errors import (
    AppException,
    BadRequestException,
    EntityAlreadyExistsException,
    EntityNotFoundException,
    ForbiddenException,
    ValidationException,
)
from backend.exception_handlers import register_exception_handlers


def _client_raising(exc: Exception) -> TestClient:
    """Build a client for an app whose only route raises ``exc``."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise exc

    return TestClient(app, raise_server_exceptions=False)


class TestAppExceptionHandler:
    """Every domain exception is answered with its class's status and message."""

    @pytest.mark.parametrize(
        ("exc_class", "status"),
        [
            (EntityNotFoundException, 404),
            (EntityAlreadyExistsException, 409),
            (ValidationException, 400),
            (BadRequestException, 400),
            (ForbiddenException, 403),
        ],
    )
    def test_subclass_maps_to_its_status(self, exc_class, status):
        """The response carries the class's status and ``{"detail": message}``."""
        response = _client_raising(exc_class("nope")).get("/boom")

        assert response.status_code == status
        assert response.json() == {"detail": "nope"}

    def test_bare_app_exception_does_not_leak_its_message(self):
        """A 5xx domain exception gets the generic unhandled-error body."""
        response = _client_raising(AppException("secret detail")).get("/boom")

        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}
