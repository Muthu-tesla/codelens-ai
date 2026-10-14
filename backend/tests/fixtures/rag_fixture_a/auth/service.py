"""User authentication and credential verification module."""
import hashlib


def hash_password(password: str) -> str:
    """Compute cryptographic SHA-256 hash of plaintext password."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class AuthService:
    """Manages user authentication and credential verification."""

    def __init__(self) -> None:
        pass

    def verify_credentials(self, username: str, password_attempt: str, stored_hash: str) -> bool:
        """Verify user login credentials by hashing password attempt and comparing with stored hash."""
        computed_hash = hash_password(password_attempt)
        return computed_hash == stored_hash
