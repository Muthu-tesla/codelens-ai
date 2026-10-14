"""Payment processing service using PayPal."""
from typing import Any, Dict
from payments.gateway import PayPalGateway


class PaymentService:
    """Executes customer payment charges through PayPalGateway."""

    def __init__(self, gateway: PayPalGateway | None = None) -> None:
        self.gateway = gateway or PayPalGateway()

    def process_payment(self, payer_id: str, amount_cents: int) -> Dict[str, Any]:
        """Charge customer through PayPal digital wallet."""
        txn_id = self.gateway.process_transaction(payer_id, amount_cents)
        return {"transaction_id": txn_id, "amount": amount_cents, "provider": "paypal"}
