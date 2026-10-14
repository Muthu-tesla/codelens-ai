"""Orders API endpoints router."""
from typing import Any, Dict
from orders.service import OrderService


def create_order_endpoint(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """POST /orders - Handles new customer order creation requests."""
    order_service = OrderService()
    customer_id = request_data.get("customer_id", 1)
    item_id = request_data.get("item_id", "prod_123")
    quantity = request_data.get("quantity", 1)
    price = request_data.get("price", 10.0)
    card_token = request_data.get("card_token", "tok_visa")
    return OrderService.create_order(
        order_service,
        customer_id=customer_id,
        item_id=item_id,
        quantity=quantity,
        price=price,
        card_token=card_token,
    )
