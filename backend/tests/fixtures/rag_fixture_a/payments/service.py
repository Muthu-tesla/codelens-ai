"""Payment processing service."""
from typing import Any, Dict
from payments.gateway import StripeGateway


class PaymentService:
    """Orchestrates customer payment processing and gateway settlement."""

    def __init__(self, gateway: StripeGateway | None = None) -> None:
        self.gateway = gateway or StripeGateway()

    def process_payment(self, card_token: str, amount_cents: int) -> Dict[str, Any]:
        """Charge customer card through Stripe gateway and return payment transaction."""
        charge_id = StripeGateway.charge_card(self.gateway, card_token, amount_cents)
        return {
            "charge_id": charge_id,
            "amount": amount_cents,
            "status": "success",
        }
