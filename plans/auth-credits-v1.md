# Auth + Credits System

## Context

BetterCV is currently stateless — no user accounts, all state in Django sessions. This plan adds real user accounts with email/password + magic link authentication, and a credit system where users purchase credits (via Lemon Squeezy) consumed each time they trigger a Claude API call.

---

## Architecture Decisions

- **No custom User model** — `db.sqlite3` already has auth migrations applied. Use Django's default `User` + a `UserProfile` (OneToOne) for credits.
- **Email as username** — custom `EmailBackend` authenticates by `email`. Username is set to email on registration and never shown.
- **Magic links** — `django-sesame`: signed, single-use, time-limited tokens. No extra model needed.
- **Payments** — Lemon Squeezy (merchant-of-record; handles global taxes). Direct checkout URL redirect + webhook. No Python SDK.
- **Credits** — 1 credit per Claude API call. 10 free credits on signup.
- **Credit deduction** — atomic `select_for_update()` before the SSE generator starts (not inside it).

---

## New Packages

```
uv add django-sesame
```

---

## Phase 1: Accounts App

### New app: `apps/accounts/`

#### Models (`apps/accounts/models.py`)

```python
class UserProfile(models.Model):
    user    = models.OneToOneField(User, on_delete=CASCADE, related_name='profile')
    credits = models.IntegerField(default=0)

class CreditTransaction(models.Model):
    TX_TYPES = [('signup_bonus','Signup Bonus'),('purchase','Purchase'),
                ('usage','Usage'),('refund','Refund')]
    user           = models.ForeignKey(User, on_delete=CASCADE, related_name='credit_transactions')
    amount         = models.IntegerField()           # signed: negative=usage, positive=grant
    description    = models.CharField(max_length=255)
    tx_type        = models.CharField(max_length=20, choices=TX_TYPES)
    created_at     = models.DateTimeField(auto_now_add=True)
    lemon_order_id = models.CharField(max_length=64, blank=True, default='')  # for webhook idempotency
    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', '-created_at'])]
```

#### Auth backend (`apps/accounts/backends.py`)

`EmailBackend(ModelBackend)` — looks up `User` by `email`, handles `MultipleObjectsReturned` safely (returns `None`).

`AUTHENTICATION_BACKENDS` in `settings/base.py`:
```python
['apps.accounts.backends.EmailBackend', 'sesame.backends.ModelBackend']
```

#### Credits module (`apps/accounts/credits.py`)

- `deduct_credit(user, amount=1, description='') -> bool` — `select_for_update()` + atomic; returns `False` if insufficient (no deduction, no transaction).
- `grant_credits(user, amount, description, tx_type, lemon_order_id='')` — always succeeds, creates transaction.
- `check_credits(user, amount=1) -> bool` — non-locking fast check.

#### `post_save` signal (`apps/accounts/signals.py`, connected in `AccountsConfig.ready()`)

Creates `UserProfile(user=instance, credits=0)` on new `User`. The 10-credit signup grant happens explicitly in the registration **view** (not signal) so it is testable and auditable.

#### Views (`apps/accounts/views.py`)

| View | Method | Action |
|---|---|---|
| `register` | POST | Create user → grant 10 credits → login → redirect `/home/` |
| `login_view` | GET/POST | Email + password form |
| `send_magic_link` | POST | Generate sesame token, send email with link |
| `magic_link_login` | GET | Validate token via sesame, login, redirect |
| `logout_view` | POST | Logout → redirect `/` |
| `account` | GET | Credit balance + last 20 transactions (`@login_required`) |
| `buy_credits` | GET | Package cards with Lemon Squeezy checkout URLs |
| `lemon_squeezy_webhook` | POST | Receive payment confirmation, grant credits |
| `payment_success` | GET | Confirmation page |
| `payment_cancel` | GET | Redirect to `/accounts/buy/` |

#### URL structure (`/accounts/` prefix, added to `ats_analyzer/urls.py`)

```
register/
login/
logout/
magic-link/send/
magic-link/login/
                              → account dashboard
buy/
webhooks/lemon-squeezy/
payment/success/
payment/cancel/
```

#### Settings additions (`settings/base.py`)

```python
SESAME_MAX_AGE = 900          # 15-minute magic links
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/home/'
LOGOUT_REDIRECT_URL = '/'
```

---

## Phase 2: Protect Tool Endpoints + Deduct Credits

### HTMX-aware login required

Create `apps/shared/decorators.py` → `htmx_login_required`:
- If `HX-Request` header present → `HttpResponse(status=204, headers={'HX-Redirect': login_url})`.
- Otherwise → standard 302 to `LOGIN_URL`.

Apply to: all tool `index` views, all `stream` views, and `coach/parse`.

### SSE streaming views (4 endpoints)

Applies to `analyzer/views.py`, `coach/views.py` (stream), `compare/views.py`, `writer/views.py`.

Credit deduction happens **before** the generator is created — never inside it (generators may be retried by the browser's EventSource; deducting inside would double-charge):

```python
def stream(request):
    nonce_data = sess.nonce(request.session).pop(key)

    if not deduct_credit(request.user, 1, '<tool> usage'):
        def err():
            yield 'event: chunk\ndata: <div class="result-error credits-error">No credits remaining. <a href="/accounts/buy/">Buy credits</a></div>\n\n'
            yield 'event: done\ndata: \n\n'
        return StreamingHttpResponse(err(), content_type='text/event-stream',
                                     headers={'Cache-Control': 'no-cache'})

    def event_stream(): ...   # unchanged
    return StreamingHttpResponse(event_stream(), ...)
```

**Compare note**: 1 credit covers both the streaming analysis + the metadata tool call. Don't double-charge.

### Non-streaming view (`POST /coach/parse/`)

```python
if not deduct_credit(request.user, 1, 'Coach — parse CV'):
    return HttpResponse(
        '<div class="result-error credits-error">No credits remaining. <a href="/accounts/buy/">Buy credits</a></div>',
        status=402,
    )
```

HTMX swaps 402 responses due to `"responseHandling": [{"code":".*", "swap": true}]` in `base.html`.

### `base.html` header update (lines 295–303)

Add right-aligned user section after `<nav>`:
```html
<div class="user-section">
  {% if user.is_authenticated %}
    <span class="credit-badge">{{ user.profile.credits }} credits</span>
    <a href="/accounts/" class="nav-link">{{ user.email }}</a>
    <form method="POST" action="/accounts/logout/" style="display:inline">
      {% csrf_token %}
      <button type="submit" class="nav-link btn-ghost">Logout</button>
    </form>
  {% else %}
    <a href="/accounts/login/" class="nav-link">Login</a>
    <a href="/accounts/register/" class="nav-link">Register</a>
  {% endif %}
</div>
```

Also update `landing.html` (standalone, doesn't extend `base.html`) with login/register links.

---

## Phase 3: Lemon Squeezy Payments

### Settings (`base.py`)

```python
LEMON_SQUEEZY_WEBHOOK_SECRET = env('LEMON_SQUEEZY_WEBHOOK_SECRET')

CREDIT_PACKAGES = [
    {'id': 'starter',  'credits': 20,  'price_usd': 5,  'variant_id': env('LS_VARIANT_STARTER')},
    {'id': 'standard', 'credits': 50,  'price_usd': 10, 'variant_id': env('LS_VARIANT_STANDARD')},
    {'id': 'pro',      'credits': 120, 'price_usd': 20, 'variant_id': env('LS_VARIANT_PRO')},
]
```

### `apps/accounts/lemon_squeezy.py`

- `build_checkout_url(variant_id, user_id, email)` — appends `?checkout[custom][user_id]=<id>&checkout[email]=<email>` to the LS hosted checkout URL. The `user_id` is returned verbatim in the webhook's `meta.custom_data`.
- `verify_webhook_signature(body: bytes, signature: str) -> bool` — HMAC-SHA256 against `LEMON_SQUEEZY_WEBHOOK_SECRET`.

### Buy page (`/accounts/buy/`)

Renders package cards. Each card's CTA is a plain `<a href="{{ pkg.checkout_url }}">` — full-page redirect to LS checkout. No JS embed.

### Webhook (`POST /accounts/webhooks/lemon-squeezy/`, `@csrf_exempt`)

1. Verify HMAC → 401 if invalid.
2. Ignore non-`order_created` events (return 200).
3. Extract `meta.custom_data.user_id`, `data.id` (order_id), `variant_id`.
4. **Idempotency**: `CreditTransaction.objects.filter(lemon_order_id=order_id).exists()` → return 200 if already processed.
5. Look up user; look up credits from `CREDIT_PACKAGES` by `variant_id`.
6. `grant_credits(user, credits, description, tx_type='purchase', lemon_order_id=order_id)`.

---

## Files to Create

```
apps/accounts/__init__.py
apps/accounts/apps.py
apps/accounts/models.py
apps/accounts/admin.py
apps/accounts/backends.py
apps/accounts/credits.py
apps/accounts/lemon_squeezy.py
apps/accounts/signals.py
apps/accounts/forms.py
apps/accounts/views.py
apps/accounts/urls.py
apps/accounts/migrations/__init__.py
apps/accounts/migrations/0001_initial.py
apps/accounts/templates/accounts/
    register.html  login.html  account.html  buy.html
    magic_link_sent.html  payment_success.html  payment_cancel.html
apps/accounts/tests/__init__.py
apps/accounts/tests/test_models.py
apps/accounts/tests/test_credits.py
apps/accounts/tests/test_views.py
apps/accounts/tests/test_webhook.py
apps/shared/decorators.py
```

## Files to Modify

```
ats_analyzer/settings/base.py       INSTALLED_APPS, AUTHENTICATION_BACKENDS, sesame/LS settings
ats_analyzer/settings/production.py Add SMTP email backend (EMAIL_HOST etc. via env)
ats_analyzer/urls.py                Add path('accounts/', include('apps.accounts.urls'))
apps/home/templates/home/base.html  Header user section + .credit-badge / .credits-error styles
apps/home/templates/home/landing.html  Login/register links
apps/analyzer/views.py              @htmx_login_required on index + stream; deduct_credit in stream
apps/coach/views.py                 @htmx_login_required on index, parse, stream; deduct_credit in both
apps/compare/views.py               @htmx_login_required on index + stream; deduct_credit in stream
apps/writer/views.py                @htmx_login_required on index + stream; deduct_credit in stream
pyproject.toml                      Add django-sesame
```

---

## Testing Updates

Existing tool view tests need a `setUp`:

```python
def setUp(self):
    self.user = User.objects.create_user(username='t@t.com', email='t@t.com', password='pass')
    grant_credits(self.user, 100, 'Test credits', tx_type='signup_bonus')
    self.client.force_login(self.user)
```

Add zero-credits path per tool:

```python
def test_stream_no_credits_returns_error_sse(self):
    self.user.profile.credits = 0
    self.user.profile.save()
    key = self._setup_session()
    response = self.client.get(f'/analyzer/analyze/stream/?key={key}')
    content = b''.join(response.streaming_content).decode()
    self.assertIn('credits-error', content)
    self.assertIn('event: done', content)
```

---

## Verification Checklist

- [ ] `make test` — all existing tests pass after auth updates.
- [ ] Register → confirm 10-credit transaction in Django admin.
- [ ] Use each tool once → credits decremented, transaction logged.
- [ ] Drain credits to 0 → "no credits" SSE error appears in each tool.
- [ ] Magic link: enter email → token appears in console → click → logged in, token reuse fails.
- [ ] Webhook: POST signed `order_created` → credits granted. POST again → idempotent.

---

## Notes

- **SQLite + `select_for_update()`**: serializes at the connection level (no row-level locking). Fine for single-server deployment. When migrating to PostgreSQL, gains true row-level locking automatically.
- **Magic link in development**: `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'` is already set in `development.py`. Token URLs will print to the terminal.
- **Magic link in production**: Needs an SMTP/transactional email provider. Recommended: Mailgun or Amazon SES. Add `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` to `.env` and configure `production.py`.
- **LS webhook in development**: Lemon Squeezy can't reach `localhost`. Use `ngrok` or the LS webhook simulator for local testing.
- **Landing page**: `landing.html` is standalone (not extending `base.html`). It needs its own auth link additions.
