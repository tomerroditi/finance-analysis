"""
Custom application exceptions.
"""


class AppException(Exception):
    """Base exception for the application."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class EntityNotFoundException(AppException):
    """Raised when a record is not found."""

    pass


class EntityAlreadyExistsException(AppException):
    """Raised when a record already exists."""

    pass


class ValidationException(AppException):
    """Raised for invalid inputs."""

    pass
