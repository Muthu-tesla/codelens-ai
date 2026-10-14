"""Authentication domain models."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class UserCredentials:
    """Represents login credentials and password metadata."""
    username: str
    password_hash: str
    salt: str

    def verify_password(self, candidate_password: str) -> bool:
        """Compare candidate password against stored hash."""
        import hashlib
        combined = (candidate_password + self.salt).encode("utf-8")
        return hashlib.sha256(combined).hexdigest() == self.password_hash


@dataclass
class SessionToken:
    """Session token model representing authenticated client identity."""
    token: str
    username: str
    expires_at: datetime
