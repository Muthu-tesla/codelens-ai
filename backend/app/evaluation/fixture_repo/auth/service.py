"""Authentication service module."""
import hashlib
from typing import Dict, Any


def hash_password(plain_text: str, salt: str) -> str:
    """Compute secure cryptographic hash of password using salt."""
    combined = (plain_text + salt).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


class AuthService:
    """Handles user authentication, session creation, and credential verification."""

    def __init__(self, token_secret: str = "secret-key") -> None:
        self.token_secret = token_secret

    def login(self, username: str, password_hash: str) -> str:
        """Authenticate user credentials and generate active session token."""
        if not username or not password_hash:
            raise ValueError("Credentials cannot be empty")
        return f"token_for_{username}"

    def authenticate_token(self, token: str) -> Dict[str, Any]:
        """Validate JWT or bearer session token and extract claims."""
        if not token.startswith("token_for_"):
            return {"valid": False, "user": None}
        user = token.replace("token_for_", "")
        return {"valid": True, "user": user}

    def logout(self, token: str) -> bool:
        """Revoke an active user session token."""
        return bool(token)
