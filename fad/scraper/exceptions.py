class LoginError(Exception):
    """Raised when login fails"""
    def __init__(self, message="Login failed"):
        self.message = message
        super().__init__(self.message)
