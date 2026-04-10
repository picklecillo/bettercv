import hashlib
import hmac
from urllib.parse import urlencode

from django.conf import settings


def build_checkout_url(product_id: str, variant_id: str, user_id: int, user_email: str) -> str:
    """Build a Lemon Squeezy hosted checkout URL with user metadata embedded."""
    params = urlencode({
        'checkout[custom][user_id]': user_id,
        'checkout[email]': user_email,
        # 'enabled': variant_id,
    })
    return f"https://bettercv.lemonsqueezy.com/buy/{product_id}/?{params}"


def verify_webhook_signature(body: bytes, header_signature: str) -> bool:
    """Verify Lemon Squeezy webhook HMAC-SHA256 signature."""
    secret = settings.LEMON_SQUEEZY_WEBHOOK_SECRET.encode()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header_signature)
