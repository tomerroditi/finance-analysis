from enum import Enum


class ErrorType(str, Enum):
    """Error categories matching upstream israeli-bank-scrapers."""
    INVALID_PASSWORD = "INVALID_PASSWORD"
    CHANGE_PASSWORD = "CHANGE_PASSWORD"
    ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED"
    TWO_FACTOR_RETRIEVER_MISSING = "TWO_FACTOR_RETRIEVER_MISSING"
    TIMEOUT = "TIMEOUT"
    GENERIC = "GENERIC"
    GENERAL = "GENERAL_ERROR"


class ScraperError(Exception):
    """Base exception for all scraper errors."""
    error_type: ErrorType = ErrorType.GENERAL

    def __init__(self, message: str = "", error_type: ErrorType | None = None):
        super().__init__(message)
        if error_type:
            self.error_type = error_type


class CredentialsError(ScraperError):
    error_type = ErrorType.INVALID_PASSWORD


class PasswordChangeError(ScraperError):
    error_type = ErrorType.CHANGE_PASSWORD


class AccountBlockedError(ScraperError):
    error_type = ErrorType.ACCOUNT_BLOCKED


class TwoFactorError(ScraperError):
    error_type = ErrorType.TWO_FACTOR_RETRIEVER_MISSING


class TimeoutError(ScraperError):
    error_type = ErrorType.TIMEOUT


class ConnectionError(ScraperError):
    error_type = ErrorType.GENERIC
