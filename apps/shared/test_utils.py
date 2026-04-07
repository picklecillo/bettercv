"""Shared test utilities."""
from django.contrib.auth import get_user_model

from apps.accounts.credits import grant_credits
from apps.accounts.models import CreditTransaction, UserProfile


class AuthenticatedMixin:
    """
    Mixin for TestCase classes that test views requiring login.
    Creates a user with 100 credits and logs them in via force_login.
    """

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.user = User.objects.create_user(
            username='test@test.com',
            email='test@test.com',
            password='testpass123',
        )
        grant_credits(
            self.user,
            100,
            'Test setup credits',
            tx_type=CreditTransaction.TxType.SIGNUP_BONUS,
        )
        self.client.force_login(self.user)


class ZeroCreditsMixin:
    """
    Mixin for TestCase classes that test credit-gated views with an empty balance.
    Creates an authenticated user whose profile has 0 credits.
    """

    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.user = User.objects.create_user(
            username='zero@test.com',
            email='zero@test.com',
            password='testpass123',
        )
        # Signal creates UserProfile with credits=0 — no grant_credits call needed.
        self.client.force_login(self.user)
