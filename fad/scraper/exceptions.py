class ScraperError(Exception):
    """Base exception for all scraper errors"""
    def __init__(self, message="Scraper error", original_error=None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)


class LoginError(ScraperError):
    """Raised when login fails"""
    def __init__(self, message="Login failed", original_error=None):
        super().__init__(message, original_error)


class CredentialsError(LoginError):
    """Raised when there's an issue with the credentials"""
    def __init__(self, message="Invalid credentials", original_error=None):
        super().__init__(message, original_error)


class ConnectionError(ScraperError):
    """Raised when there's a connection issue"""
    def __init__(self, message="Connection error", original_error=None):
        super().__init__(message, original_error)


class TimeoutError(ScraperError):
    """Raised when a scraping operation times out"""
    def __init__(self, message="Operation timed out", original_error=None):
        super().__init__(message, original_error)


class DataError(ScraperError):
    """Raised when there's an issue with the scraped data"""
    def __init__(self, message="Data error", original_error=None):
        super().__init__(message, original_error)


class AccountError(ScraperError):
    """Raised when there's an issue with the account (blocked, suspended, etc.)"""
    def __init__(self, message="Account error", original_error=None):
        super().__init__(message, original_error)


class ServiceError(ScraperError):
    """Raised when the service is unavailable (maintenance, etc.)"""
    def __init__(self, message="Service unavailable", original_error=None):
        super().__init__(message, original_error)


class RateLimitError(ScraperError):
    """Raised when the scraper hits a rate limit or too many requests"""
    def __init__(self, message="Rate limit exceeded", original_error=None):
        super().__init__(message, original_error)


class SecurityError(ScraperError):
    """Raised when there's a security-related issue (CAPTCHA, additional verification, etc.)"""
    def __init__(self, message="Security verification required", original_error=None):
        super().__init__(message, original_error)
