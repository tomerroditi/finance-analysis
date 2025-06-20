from enum import Enum, auto

class ErrorType(Enum):
    """
    Enum defining standardized error types for scrapers.

    These error types are used to categorize errors in a consistent way
    between Python and Node.js code.

    Attributes
    ----------
    GENERAL : auto
        General scraper error, not fitting any specific category.
    CREDENTIALS : auto
        Error related to invalid credentials.
    CONNECTION : auto
        Error related to network connection issues.
    TIMEOUT : auto
        Error related to operation timeouts.
    DATA : auto
        Error related to data processing or parsing.
    LOGIN : auto
        Error related to the login process.
    PASSWORD_CHANGE : auto
        Error indicating that a password change is required.
    ACCOUNT : auto
        Error related to account status (blocked, suspended, etc.).
    SERVICE : auto
        Error related to service availability.
    RATE_LIMIT : auto
        Error related to rate limiting or too many requests.
    SECURITY : auto
        Error related to security measures (CAPTCHA, verification, etc.).
    """
    GENERAL = auto()
    CREDENTIALS = auto()
    CONNECTION = auto()
    TIMEOUT = auto()
    DATA = auto()
    LOGIN = auto()
    PASSWORD_CHANGE = auto()
    ACCOUNT = auto()
    SERVICE = auto()
    RATE_LIMIT = auto()
    SECURITY = auto()


class ScraperError(Exception):
    """Base exception for all scraper errors"""
    error_type = ErrorType.GENERAL

    def __init__(self, message="Scraper error", original_error=None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class LoginError(ScraperError):
    """Raised when login fails"""
    error_type = ErrorType.LOGIN

    def __init__(self, message="Login failed", original_error=None):
        super().__init__(message, original_error)


class CredentialsError(LoginError):
    """Raised when there's an issue with the credentials"""
    error_type = ErrorType.CREDENTIALS

    def __init__(self, message="Invalid credentials", original_error=None):
        super().__init__(message, original_error)


class ConnectionError(ScraperError):
    """Raised when there's a connection issue"""
    error_type = ErrorType.CONNECTION

    def __init__(self, message="Connection error", original_error=None):
        super().__init__(message, original_error)


class TimeoutError(ScraperError):
    """Raised when a scraping operation times out"""
    error_type = ErrorType.TIMEOUT

    def __init__(self, message="Operation timed out", original_error=None):
        super().__init__(message, original_error)


class DataError(ScraperError):
    """Raised when there's an issue with the scraped data"""
    error_type = ErrorType.DATA

    def __init__(self, message="Data error", original_error=None):
        super().__init__(message, original_error)


class AccountError(ScraperError):
    """Raised when there's an issue with the account (blocked, suspended, etc.)"""
    error_type = ErrorType.ACCOUNT

    def __init__(self, message="Account error", original_error=None):
        super().__init__(message, original_error)


class ServiceError(ScraperError):
    """Raised when the service is unavailable (maintenance, etc.)"""
    error_type = ErrorType.SERVICE

    def __init__(self, message="Service unavailable", original_error=None):
        super().__init__(message, original_error)


class RateLimitError(ScraperError):
    """Raised when the scraper hits a rate limit or too many requests"""
    error_type = ErrorType.RATE_LIMIT

    def __init__(self, message="Rate limit exceeded", original_error=None):
        super().__init__(message, original_error)


class SecurityError(ScraperError):
    """Raised when there's a security-related issue (CAPTCHA, additional verification, etc.)"""
    error_type = ErrorType.SECURITY

    def __init__(self, message="Security verification required", original_error=None):
        super().__init__(message, original_error)


class PasswordChangeError(CredentialsError):
    """Raised when a password change is required"""
    error_type = ErrorType.PASSWORD_CHANGE

    def __init__(self, message="Password change required", original_error=None):
        super().__init__(message, original_error)
