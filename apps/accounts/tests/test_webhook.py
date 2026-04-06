import hashlib
import hmac
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.credits import grant_credits
from apps.accounts.models import CreditTransaction, UserProfile

User = get_user_model()

WEBHOOK_SECRET = 'test-secret-key'

FAKE_PACKAGES = [
    {'id': 'starter', 'label': 'Starter', 'credits': 20, 'price_usd': 5, 'variant_id': 'var-111'},
    {'id': 'standard', 'label': 'Standard', 'credits': 50, 'price_usd': 10, 'variant_id': 'var-222'},
]


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _payload(user_id, order_id='order-001', variant_id='var-111'):
    return {
        'meta': {
            'event_name': 'order_created',
            'custom_data': {'user_id': user_id},
        },
        'data': {
            'id': order_id,
            'attributes': {
                'first_order_item': {'variant_id': variant_id},
            },
        },
    }


@override_settings(
    LEMON_SQUEEZY_WEBHOOK_SECRET=WEBHOOK_SECRET,
    CREDIT_PACKAGES=FAKE_PACKAGES,
)
class WebhookTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='buyer@test.com', email='buyer@test.com', password='pass'
        )

    def _post(self, payload, secret=WEBHOOK_SECRET):
        body = json.dumps(payload).encode()
        sig = _sign(body, secret)
        return self.client.post(
            '/accounts/webhooks/lemon-squeezy/',
            data=body,
            content_type='application/json',
            HTTP_X_SIGNATURE=sig,
        )

    def test_valid_order_grants_credits(self):
        payload = _payload(self.user.id)
        self._post(payload)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.credits, 20)

    def test_valid_order_creates_transaction(self):
        payload = _payload(self.user.id)
        self._post(payload)
        tx = CreditTransaction.objects.get(user=self.user)
        self.assertEqual(tx.tx_type, CreditTransaction.TxType.PURCHASE)
        self.assertEqual(tx.amount, 20)
        self.assertEqual(tx.lemon_order_id, 'order-001')

    def test_valid_order_returns_200(self):
        response = self._post(_payload(self.user.id))
        self.assertEqual(response.status_code, 200)

    def test_invalid_signature_returns_401(self):
        payload = _payload(self.user.id)
        body = json.dumps(payload).encode()
        bad_sig = 'deadbeef' * 8
        response = self.client.post(
            '/accounts/webhooks/lemon-squeezy/',
            data=body,
            content_type='application/json',
            HTTP_X_SIGNATURE=bad_sig,
        )
        self.assertEqual(response.status_code, 401)

    def test_invalid_signature_does_not_grant_credits(self):
        payload = _payload(self.user.id)
        body = json.dumps(payload).encode()
        self.client.post(
            '/accounts/webhooks/lemon-squeezy/',
            data=body,
            content_type='application/json',
            HTTP_X_SIGNATURE='bad',
        )
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.credits, 0)

    def test_non_order_created_event_returns_200_without_credits(self):
        payload = {
            'meta': {'event_name': 'subscription_created', 'custom_data': {}},
            'data': {},
        }
        response = self._post(payload)
        self.assertEqual(response.status_code, 200)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.credits, 0)

    def test_duplicate_order_id_is_idempotent(self):
        payload = _payload(self.user.id, order_id='dup-order')
        self._post(payload)
        self._post(payload)  # second time
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.credits, 20)  # credited only once

    def test_duplicate_order_creates_only_one_transaction(self):
        payload = _payload(self.user.id, order_id='dup-order-2')
        self._post(payload)
        self._post(payload)
        self.assertEqual(CreditTransaction.objects.filter(user=self.user).count(), 1)

    def test_unknown_user_id_returns_404(self):
        payload = _payload(user_id=99999)
        response = self._post(payload)
        self.assertEqual(response.status_code, 404)

    def test_unknown_variant_id_returns_400(self):
        payload = _payload(self.user.id, variant_id='unknown-variant')
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)

    def test_missing_user_id_returns_400(self):
        payload = {
            'meta': {'event_name': 'order_created', 'custom_data': {}},
            'data': {
                'id': 'order-x',
                'attributes': {'first_order_item': {'variant_id': 'var-111'}},
            },
        }
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)

    def test_standard_variant_grants_50_credits(self):
        payload = _payload(self.user.id, order_id='order-std', variant_id='var-222')
        self._post(payload)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.credits, 50)
