"""Custom application exceptions and the HTTP status each one maps to.

``backend.exception_handlers`` turns any :class:`AppException` into a JSON
``{"detail": message}`` response carrying the class's ``status_code``.
"""


class AppException(Exception):
    """Base exception for the application.

    Attributes
    ----------
    status_code : int
        HTTP status the exception is answered with. The base class is never
        raised directly; at 500 it gets the generic, message-free body.
    """

    status_code: int = 500

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class EntityNotFoundException(AppException):
    """Raised when a record is not found."""

    status_code = 404


class EntityAlreadyExistsException(AppException):
    """Raised when a record already exists."""

    status_code = 409


class ValidationException(AppException):
    """Raised for invalid inputs."""

    status_code = 400


class BadRequestException(AppException):
    """Raised for bad requests."""

    status_code = 400


class ForbiddenException(AppException):
    """Raised when the caller may not perform the requested action."""

    status_code = 403
