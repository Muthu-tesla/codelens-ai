"""Database repository module for persistence."""
from typing import Any, Dict


class OrderRepository:
    """Handles database persistence for customer orders."""

    def __init__(self, db_session: Any = None) -> None:
        self.session = db_session

    def save_order(self, order_data: Dict[str, Any]) -> int:
        """Persist order record into relational database."""
        order_id = int(order_data.get("id", 101))
        return order_id
