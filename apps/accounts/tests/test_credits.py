from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.credits import check_credits, deduct_credit, grant_credits
from apps.accounts.models import CreditTransaction, UserProfile

User = get_user_model()


def _make_user(email='a@test.com'):
    return User.objects.create_user(username=email, email=email, password='pass')


class DeductCreditTests(TestCase):

    def test_deduct_with_sufficient_balance_returns_true(self):
        user = _make_user()
        grant_credits(user, 5, 'setup', tx_type=CreditTransaction.TxType.SIGNUP_BONUS)
        result = deduct_credit(user, 1, 'test usage')
        self.assertTrue(result)

    def test_deduct_reduces_balance(self):
        user = _make_user()
        grant_credits(user, 5, 'setup', tx_type=CreditTransaction.TxType.SIGNUP_BONUS)
        deduct_credit(user, 2, 'test')
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.credits, 3)

    def test_deduct_creates_negative_transaction(self):
        user = _make_user()
        grant_credits(user, 5, 'setup', tx_type=CreditTransaction.TxType.SIGNUP_BONUS)
        deduct_credit(user, 1, 'tool usage')
        tx = CreditTransaction.objects.filter(user=user, tx_type=CreditTransaction.TxType.USAGE).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.amount, -1)
        self.assertEqual(tx.description, 'tool usage')

    def test_deduct_with_zero_balance_returns_false(self):
        user = _make_user()
        result = deduct_credit(user, 1, 'test')
        self.assertFalse(result)

    def test_deduct_with_zero_balance_does_not_modify_profile(self):
        user = _make_user()
        deduct_credit(user, 1, 'test')
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.credits, 0)

    def test_deduct_with_zero_balance_creates_no_transaction(self):
        user = _make_user()
        deduct_credit(user, 1, 'test')
        self.assertEqual(CreditTransaction.objects.filter(user=user).count(), 0)

    def test_deduct_with_insufficient_balance_returns_false(self):
        user = _make_user()
        grant_credits(user, 2, 'setup', tx_type=CreditTransaction.TxType.SIGNUP_BONUS)
        result = deduct_credit(user, 5, 'test')
        self.assertFalse(result)

    def test_deduct_with_no_profile_returns_false(self):
        user = User.objects.create_user(username='b@test.com', email='b@test.com', password='pass')
        UserProfile.objects.filter(user=user).delete()
        result = deduct_credit(user, 1, 'test')
        self.assertFalse(result)

    def test_exact_balance_deduction_succeeds(self):
        user = _make_user()
        grant_credits(user, 3, 'setup', tx_type=CreditTransaction.TxType.SIGNUP_BONUS)
        result = deduct_credit(user, 3, 'test')
        self.assertTrue(result)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.credits, 0)


class GrantCreditsTests(TestCase):

    def test_grant_increases_balance(self):
        user = _make_user()
        grant_credits(user, 10, 'welcome', tx_type=CreditTransaction.TxType.SIGNUP_BONUS)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.credits, 10)

    def test_grant_creates_positive_transaction(self):
        user = _make_user()
        grant_credits(user, 10, 'welcome', tx_type=CreditTransaction.TxType.SIGNUP_BONUS)
        tx = CreditTransaction.objects.get(user=user)
        self.assertEqual(tx.amount, 10)
        self.assertEqual(tx.tx_type, CreditTransaction.TxType.SIGNUP_BONUS)

    def test_grant_with_lemon_order_id_stored(self):
        user = _make_user()
        grant_credits(user, 50, 'purchase', tx_type=CreditTransaction.TxType.PURCHASE, lemon_order_id='order-123')
        tx = CreditTransaction.objects.get(user=user)
        self.assertEqual(tx.lemon_order_id, 'order-123')

    def test_multiple_grants_accumulate(self):
        user = _make_user()
        grant_credits(user, 10, 'first', tx_type=CreditTransaction.TxType.SIGNUP_BONUS)
        grant_credits(user, 20, 'second', tx_type=CreditTransaction.TxType.PURCHASE)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.credits, 30)


class CheckCreditsTests(TestCase):

    def test_returns_true_when_sufficient(self):
        user = _make_user()
        grant_credits(user, 5, 'setup', tx_type=CreditTransaction.TxType.SIGNUP_BONUS)
        self.assertTrue(check_credits(user, 3))

    def test_returns_false_when_insufficient(self):
        user = _make_user()
        self.assertFalse(check_credits(user, 1))

    def test_returns_false_when_no_profile(self):
        user = User.objects.create_user(username='c@test.com', email='c@test.com', password='pass')
        UserProfile.objects.filter(user=user).delete()
        self.assertFalse(check_credits(user, 1))

    def test_exact_amount_returns_true(self):
        user = _make_user()
        grant_credits(user, 3, 'setup', tx_type=CreditTransaction.TxType.SIGNUP_BONUS)
        self.assertTrue(check_credits(user, 3))
