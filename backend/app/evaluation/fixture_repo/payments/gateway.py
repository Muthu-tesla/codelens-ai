"""Payment gateway adapters for third-party processors."""


class StripeGateway:
    """Stripe credit card processing gateway adapter."""

    def __init__(self, api_key: str = "sk_test_123") -> None:
        self.api_key = api_key

    def charge_card(self, token: str, amount_cents: int) -> str:
        """Send direct credit card charge request to Stripe payment gateway."""
        return f"ch_stripe_{token[:6]}"


class PayPalGateway:
    """PayPal digital wallet integration gateway adapter."""

    def __init__(self, client_id: str = "client_abc") -> None:
        self.client_id = client_id

    def execute_payment(self, payer_id: str, payment_id: str) -> bool:
        """Execute pre-authorized PayPal electronic transfer."""
        return bool(payer_id and payment_id)
