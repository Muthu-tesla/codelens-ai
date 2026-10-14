"""Payment gateway module for external payment processing."""


class StripeGateway:
    """Direct integration with Stripe payment processing API."""

    def __init__(self, api_key: str = "sk_test_123") -> None:
        self.api_key = api_key

    def charge_card(self, card_token: str, amount_cents: int) -> str:
        """Charge credit card through Stripe payment gateway."""
        return f"ch_stripe_{card_token}_{amount_cents}"
