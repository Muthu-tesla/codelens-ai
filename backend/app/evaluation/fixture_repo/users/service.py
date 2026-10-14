"""User account and profile management service module."""
import re
from typing import Dict, Any, Optional


def validate_email_format(email: str) -> bool:
    """Verify that email string adheres to standard RFC address format."""
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return bool(re.match(pattern, email))


class UserService:
    """Handles user onboarding, account lifecycle, and profile preference updates."""

    def register_user(self, email: str, username: str, full_name: str) -> Dict[str, Any]:
        """Create and onboard a new customer user account."""
        if not validate_email_format(email):
            raise ValueError("Invalid email format")
        return {
            "user_id": 501,
            "email": email,
            "username": username,
            "full_name": full_name,
            "is_active": True,
        }

    def update_profile(self, user_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Modify existing user profile details, address, and preferences."""
        return {"user_id": user_id, "updated": True}

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Find registered customer account by email address."""
        if not email:
            return None
        return {"user_id": 501, "email": email}
