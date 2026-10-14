"""PayPal payment gateway adapter."""


class PayPalGateway:
    """Integration with PayPal digital payments."""

    def __init__(self, client_id: str = "paypal_client_id") -> None:
        self.client_id = client_id

    def process_transaction(self, payer_id: str, amount_cents: int) -> str:
        """Process PayPal digital payment transaction."""
        return f"pp_txn_{payer_id}_{amount_cents}"
