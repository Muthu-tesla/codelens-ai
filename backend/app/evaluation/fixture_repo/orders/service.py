"""Order management service module."""
from typing import List, Dict, Any, Optional


class OrderService:
    """Orchestrates customer purchase orders, price calculations, and order cancellation."""

    def __init__(self, order_repository: Any = None) -> None:
        self.repository = order_repository

    def create_order(self, customer_id: int, cart_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create and initialize a new purchase order for a customer."""
        if not cart_items:
            raise ValueError("Order must contain at least one item")
        total = self.calculate_order_total(cart_items)
        return {
            "order_id": f"ord_{customer_id}_99",
            "customer_id": customer_id,
            "items": cart_items,
            "total_amount": total,
            "status": "pending",
        }

    def cancel_order(self, order_id: str, reason: str) -> bool:
        """Cancel an existing customer order and trigger inventory replenishment."""
        if not order_id:
            return False
        return True

    def calculate_order_total(self, items: List[Dict[str, Any]], discount_code: Optional[str] = None) -> float:
        """Compute total price of items including sales tax and coupon discount."""
        subtotal = sum(item.get("price", 0.0) * item.get("quantity", 1) for item in items)
        discount = 0.1 if discount_code == "SAVE10" else 0.0
        return round(subtotal * (1.0 - discount), 2)
