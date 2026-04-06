from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase

from apps.accounts.credits import grant_credits
from apps.accounts.models import CreditTransaction, UserProfile

User = get_user_model()


class RegisterViewTests(TestCase):

    def _post(self, email='user@test.com', password1='Str0ng!pass', password2='Str0ng!pass'):
        return self.client.post('/accounts/register/', {
            'email': email,
            'password1': password1,
            'password2': password2,
        })

    def test_get_returns_200(self):
        response = self.client.get('/accounts/register/')
        self.assertEqual(response.status_code, 200)

    def test_valid_registration_creates_user(self):
        self._post()
        self.assertTrue(User.objects.filter(email='user@test.com').exists())

    def test_valid_registration_redirects_to_home(self):
        response = self._post()
        self.assertRedirects(response, '/home/', fetch_redirect_response=False)

    def test_valid_registration_creates_profile(self):
        self._post()
        user = User.objects.get(email='user@test.com')
        self.assertTrue(UserProfile.objects.filter(user=user).exists())

    def test_valid_registration_grants_10_credits(self):
        self._post()
        user = User.objects.get(email='user@test.com')
        self.assertEqual(user.profile.credits, 10)

    def test_valid_registration_creates_signup_bonus_transaction(self):
        self._post()
        user = User.objects.get(email='user@test.com')
        tx = CreditTransaction.objects.get(user=user)
        self.assertEqual(tx.tx_type, CreditTransaction.TxType.SIGNUP_BONUS)
        self.assertEqual(tx.amount, 10)

    def test_valid_registration_logs_user_in(self):
        self._post()
        response = self.client.get('/accounts/')
        self.assertEqual(response.status_code, 200)  # not redirected to login

    def test_duplicate_email_returns_form_error(self):
        User.objects.create_user(username='user@test.com', email='user@test.com', password='pass')
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'already exists', response.content)

    def test_mismatched_passwords_returns_form_error(self):
        response = self._post(password2='DifferentPass1!')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'do not match', response.content)

    def test_authenticated_user_redirected_from_register(self):
        user = User.objects.create_user(username='x@test.com', email='x@test.com', password='pass')
        self.client.force_login(user)
        response = self.client.get('/accounts/register/')
        self.assertRedirects(response, '/home/', fetch_redirect_response=False)


class LoginViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='login@test.com',
            email='login@test.com',
            password='Str0ng!pass',
        )

    def test_get_returns_200(self):
        response = self.client.get('/accounts/login/')
        self.assertEqual(response.status_code, 200)

    def test_valid_credentials_logs_in(self):
        self.client.post('/accounts/login/', {'email': 'login@test.com', 'password': 'Str0ng!pass'})
        response = self.client.get('/accounts/')
        self.assertEqual(response.status_code, 200)

    def test_valid_credentials_redirects_to_home(self):
        response = self.client.post('/accounts/login/', {
            'email': 'login@test.com',
            'password': 'Str0ng!pass',
        })
        self.assertRedirects(response, '/home/', fetch_redirect_response=False)

    def test_valid_credentials_with_next_redirects_to_next(self):
        response = self.client.post('/accounts/login/?next=/analyzer/', {
            'email': 'login@test.com',
            'password': 'Str0ng!pass',
        })
        self.assertRedirects(response, '/analyzer/', fetch_redirect_response=False)

    def test_invalid_password_returns_error(self):
        response = self.client.post('/accounts/login/', {
            'email': 'login@test.com',
            'password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid email or password', response.content)

    def test_unknown_email_returns_error(self):
        response = self.client.post('/accounts/login/', {
            'email': 'nobody@test.com',
            'password': 'Str0ng!pass',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid email or password', response.content)


class LogoutViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='out@test.com', email='out@test.com', password='pass'
        )
        self.client.force_login(self.user)

    def test_post_logs_out(self):
        self.client.post('/accounts/logout/')
        response = self.client.get('/accounts/')
        self.assertRedirects(response, '/accounts/login/?next=/accounts/', fetch_redirect_response=False)

    def test_post_redirects_to_root(self):
        response = self.client.post('/accounts/logout/')
        self.assertRedirects(response, '/', fetch_redirect_response=False)


class MagicLinkTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='magic@test.com', email='magic@test.com', password='pass'
        )

    def test_send_unknown_email_shows_sent_page(self):
        # Should not reveal whether email exists
        response = self.client.post('/accounts/magic-link/send/', {'email': 'nobody@test.com'})
        self.assertEqual(response.status_code, 200)

    def test_send_known_email_sends_email(self):
        self.client.post('/accounts/magic-link/send/', {'email': 'magic@test.com'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('magic@test.com', mail.outbox[0].to)
        self.assertIn('BetterCV', mail.outbox[0].subject)

    def test_send_known_email_shows_sent_partial(self):
        response = self.client.post('/accounts/magic-link/send/', {'email': 'magic@test.com'})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Check your inbox', response.content)

    def test_invalid_token_returns_400(self):
        response = self.client.get('/accounts/magic-link/login/?sesame=invalid-token')
        self.assertEqual(response.status_code, 400)

    def test_valid_token_logs_user_in(self):
        from urllib.parse import urlencode
        import sesame.utils
        params = urlencode(sesame.utils.get_parameters(self.user))
        response = self.client.get(f'/accounts/magic-link/login/?{params}')
        self.assertRedirects(response, '/home/', fetch_redirect_response=False)
        # Confirm the user is now logged in
        account_response = self.client.get('/accounts/')
        self.assertEqual(account_response.status_code, 200)

    def test_token_cannot_be_reused(self):
        from urllib.parse import urlencode
        import sesame.utils
        params = urlencode(sesame.utils.get_parameters(self.user))
        # Use it once
        self.client.get(f'/accounts/magic-link/login/?{params}')
        self.client.logout()
        # Try to use it again
        response = self.client.get(f'/accounts/magic-link/login/?{params}')
        self.assertEqual(response.status_code, 400)


class AccountViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='acct@test.com', email='acct@test.com', password='pass'
        )
        grant_credits(self.user, 15, 'bonus', tx_type=CreditTransaction.TxType.SIGNUP_BONUS)
        self.client.force_login(self.user)

    def test_returns_200(self):
        response = self.client.get('/accounts/')
        self.assertEqual(response.status_code, 200)

    def test_shows_credit_balance(self):
        response = self.client.get('/accounts/')
        self.assertContains(response, '15')

    def test_shows_transactions(self):
        response = self.client.get('/accounts/')
        self.assertContains(response, 'bonus')

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get('/accounts/')
        self.assertRedirects(
            response,
            '/accounts/login/?next=/accounts/',
            fetch_redirect_response=False,
        )


class NoCreditsGatingTests(TestCase):
    """Test that views return appropriate errors when user has 0 credits."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='broke@test.com', email='broke@test.com', password='pass'
        )
        # No credits granted
        self.client.force_login(self.user)

    def _setup_analyzer_nonce(self):
        from apps.shared import session as sess
        session = self.client.session
        key = sess.nonce(session).put({'resume_text': 'r', 'jd_text': 'j'})
        session.save()
        return key

    def test_analyzer_stream_no_credits_returns_sse_error(self):
        key = self._setup_analyzer_nonce()
        response = self.client.get(f'/analyzer/analyze/stream/?key={key}')
        content = b''.join(response.streaming_content).decode()
        self.assertIn('credits-error', content)
        self.assertIn('event: done', content)

    def test_coach_parse_no_credits_returns_402(self):
        from unittest.mock import patch
        from apps.coach.tests.fakes import FakeCoachService, FAKE_EXPERIENCES
        fake = FakeCoachService()
        with patch('apps.coach.views.get_coach_service', return_value=fake):
            response = self.client.post('/coach/parse/', {'cv_text': 'My CV'})
        self.assertEqual(response.status_code, 402)
        self.assertIn(b'credits-error', response.content)
