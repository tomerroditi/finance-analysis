"""Custom application exceptions, mapped to HTTP statuses in ``backend.main``."""


class AppException(Exception):
    """Base exception for the application."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class EntityNotFoundException(AppException):
    """Raised when a record is not found."""


class EntityAlreadyExistsException(AppException):
    """Raised when a record already exists."""


class ValidationException(AppException):
    """Raised for invalid inputs."""


class BadRequestException(AppException):
    """Raised for bad requests."""
