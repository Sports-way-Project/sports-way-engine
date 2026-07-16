import hashlib
import hmac
from urllib.parse import urlencode

from app.core.config import settings


class SadadClient:
    """Builds/verifies Sadad hosted-payment-page requests.

    Sadad (like most Gulf hosted-checkout gateways) works as a signed
    redirect: the merchant never touches card data — it builds a signed
    request, sends the shopper to Sadad's page, and Sadad redirects back
    with a signed result. The exact field names below follow the common
    merchant_id/terminal_id/secret_key pattern; confirm them against the
    actual integration guide Sadad gives this merchant and adjust field
    names in `build_payment_url`/`verify_callback` if they differ.
    """

    def __init__(self) -> None:
        self._merchant_id = settings.sadad_merchant_id
        self._terminal_id = settings.sadad_terminal_id
        self._secret_key = settings.sadad_secret_key
        self._base_url = settings.sadad_base_url.rstrip("/")
        self._currency = settings.sadad_currency

    def _sign(self, *parts: str) -> str:
        message = "|".join(parts)
        return hmac.new(self._secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()

    def is_configured(self) -> bool:
        return bool(self._merchant_id and self._terminal_id and self._secret_key)

    def build_payment_url(self, order_id: str, amount: float, return_url: str) -> str:
        amount_str = f"{amount:.2f}"
        signature = self._sign(self._merchant_id, self._terminal_id, order_id, amount_str, self._currency)
        params = {
            "merchant_id": self._merchant_id,
            "terminal_id": self._terminal_id,
            "order_id": order_id,
            "amount": amount_str,
            "currency": self._currency,
            "return_url": return_url,
            "signature": signature,
        }
        return f"{self._base_url}?{urlencode(params)}"

    def verify_callback(self, params: dict) -> bool:
        """Recomputes the signature Sadad should have sent back and compares
        it in constant time. Returns False (never raises) on any mismatch or
        missing field, so a malformed callback just fails closed."""
        try:
            expected = self._sign(
                params.get("merchant_id", ""),
                params.get("terminal_id", ""),
                params.get("order_id", ""),
                f"{float(params.get('amount', 0)):.2f}",
                params.get("currency", self._currency),
            )
            return hmac.compare_digest(expected, params.get("signature", ""))
        except (TypeError, ValueError):
            return False


sadad_client = SadadClient()
