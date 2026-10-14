"""Order processing service module."""
from typing import Any, Dict
from database.repository import OrderRepository
from inventory.service import InventoryService
from payments.service import PaymentService


class OrderService:
    """Coordinates order creation, inventory stock checking, payment processing, and database persistence."""

    def __init__(
        self,
        inventory_service: InventoryService | None = None,
        payment_service: PaymentService | None = None,
        order_repository: OrderRepository | None = None,
    ) -> None:
        self.inventory_service = inventory_service or InventoryService()
        self.payment_service = payment_service or PaymentService()
        self.order_repository = order_repository or OrderRepository()

    def create_order(
        self,
        customer_id: int,
        item_id: str,
        quantity: int,
        price: float,
        card_token: str = "tok_default",
    ) -> Dict[str, Any]:
        """Verify stock availability, process payment, and persist order to the database."""
        in_stock = InventoryService.check_stock(self.inventory_service, item_id, quantity)
        if not in_stock:
            raise ValueError("Item out of stock")

        amount_cents = int(price * quantity * 100)
        payment_result = PaymentService.process_payment(self.payment_service, card_token, amount_cents)

        order_data = {
            "customer_id": customer_id,
            "item_id": item_id,
            "quantity": quantity,
            "total_price": price * quantity,
            "payment_id": payment_result.get("charge_id"),
            "status": "confirmed",
        }
        order_id = OrderRepository.save_order(self.order_repository, order_data)
        order_data["id"] = order_id
        return order_data
