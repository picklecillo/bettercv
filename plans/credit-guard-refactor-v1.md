# Credit Guard Refactor — Plan

## Problem

Five credit deductions are scattered across four app view files as inline imports and
imperative branches. This creates three concrete problems:

1. **Hidden dependency.** `from apps.accounts.credits import deduct_credit` inside a function
   body is invisible to anyone reading the module's import block. Grepping for credit usage
   requires reading every view body.

2. **Coach two-phase cost undocumented.** Coach deducts 1 credit at parse AND 1 credit per
   chat turn. This is intentional but nowhere declared — no test verifies it, and there is
   no single place that states "a full coach session costs 2+ credits."

3. **No view-level credit tests.** Current tests for `test_credits.py` cover `deduct_credit`
   in isolation. No view test verifies that a successful request actually deducts credits,
   and no view test exercises the zero-credit error path.

## Chosen Interface

`CreditCost` dataclass with a `.guard()` method, plus `credit_balance()` as a test helper.

### Core types (`apps/accounts/credits.py` — additions)

```python
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    from django.http import HttpResponse, StreamingHttpResponse


@dataclass(frozen=True)
class CreditCost:
    """
    Declares the credit requirement at a call site.

    Define as a module-level constant in each view file:
        STREAM_COST = CreditCost(amount=1, description='ATS analysis')

    Use .guard() with the walrus operator in the view body:
        if resp := STREAM_COST.guard(request.user, no_credits_response):
            return resp

    Use .amount and .description in tests without any DB access:
        self.assertEqual(analyzer_views.STREAM_COST.amount, 1)
    """
    amount: int
    description: str

    def deduct(self, user: AbstractBaseUser) -> bool:
        """Atomically deduct. Returns True on success, False if insufficient."""
        return deduct_credit(user, self.amount, self.description)

    def guard(
        self,
        user: AbstractBaseUser,
        on_insufficient: Callable[[], HttpResponse | StreamingHttpResponse],
    ) -> HttpResponse | StreamingHttpResponse | None:
        """
        Deduct credits or return the appropriate error response.

        Returns None on success — caller continues normally.
        Returns on_insufficient() if the user has insufficient credits.

        The on_insufficient factory makes the error response protocol explicit
        at the call site: SSE views pass no_credits_response, non-streaming
        views pass a local HTML factory.
        """
        if not self.deduct(user):
            return on_insufficient()
        return None


def credit_balance(user: AbstractBaseUser) -> int:
    """
    Return the current credit balance for user.

    Intended for test post-condition assertions only. Never use in production
    view logic — use check_credits() there (non-locking fast-path).
    """
    try:
        return UserProfile.objects.get(user=user).credits
    except UserProfile.DoesNotExist:
        return 0
```

### Call site pattern

```python
# In each view file — module level:
STREAM_COST = CreditCost(amount=1, description='ATS analysis')

# In the view body — after nonce validation, before the expensive operation:
if resp := STREAM_COST.guard(request.user, no_credits_response):
    return resp
```

The `on_insufficient` factory is always explicit at the call site:
- SSE views: `no_credits_response` (from `apps.shared.sse`)
- Non-SSE views (coach parse): a local HTML factory defined in that view module

## How Each View Migrates

### Analyzer (`analyzer/views.py`)

```python
from apps.accounts.credits import CreditCost
from apps.shared.sse import SseStream, no_credits_response

STREAM_COST = CreditCost(amount=1, description='ATS analysis')

@htmx_login_required
def stream(request):
    key = request.GET.get("key", "")
    data = sess.nonce(request.session).pop(key)
    if not data:
        return HttpResponse("Session expired. Please submit the form again.", status=400)

    if resp := STREAM_COST.guard(request.user, no_credits_response):
        return resp

    return SseStream(
        source=get_service().stream(data["resume_text"], data["jd_text"]),
        known_errors=(ClaudeServiceError,),
    ).response()
```

### Coach (`coach/views.py`)

```python
from apps.accounts.credits import CreditCost
from apps.shared.sse import SSEEvent, SseStream, no_credits_response

PARSE_COST  = CreditCost(amount=1, description='Resume coaching — parse CV')
STREAM_COST = CreditCost(amount=1, description='Resume coaching — chat turn')

def _no_credits_html():
    return HttpResponse(
        '<div class="result-error credits-error">No credits remaining. '
        '<a href="/accounts/buy/">Buy credits</a> to continue.</div>',
        status=402,
        content_type='text/html',
    )

@htmx_login_required
@require_POST
def parse(request):
    # ... pdf/text extraction ...
    if resp := PARSE_COST.guard(request.user, _no_credits_html):
        return resp
    # ... rest unchanged ...

@htmx_login_required
def stream(request):
    key = request.GET.get("key", "")
    nonce_data = sess.nonce(request.session).pop(key)
    if not nonce_data:
        return HttpResponse("Session expired. Please try again.", status=400)

    if resp := STREAM_COST.guard(request.user, no_credits_response):
        return resp
    # ... rest unchanged ...
```

### Compare (`compare/views.py`)

```python
from apps.accounts.credits import CreditCost
from apps.shared.sse import SSEEvent, SseStream, no_credits_response

STREAM_COST = CreditCost(amount=1, description='JD comparison')

@htmx_login_required
def stream(request):
    # ... nonce pop ...
    if resp := STREAM_COST.guard(request.user, no_credits_response):
        return resp
    # ... rest unchanged ...
```

### Writer (`writer/views.py`)

```python
from apps.accounts.credits import CreditCost
from apps.shared.sse import make_sse_response, no_credits_response

STREAM_COST = CreditCost(amount=1, description='Resume Writer — YAML generation')

@htmx_login_required
@require_GET
def stream(request):
    # ... nonce pop ...
    if resp := STREAM_COST.guard(request.user, no_credits_response):
        return resp
    # ... rest unchanged ...
```

## Implementation Steps

### Step 1 — Add `CreditCost` and `credit_balance` to `apps/accounts/credits.py`

Add both to the existing module — no new file needed. `credit_balance` is safe to
add immediately since it is purely additive.

No existing code is touched in this step.

### Step 2 — Add `ZeroCreditsMixin` to `apps/shared/test_utils.py`

```python
class ZeroCreditsMixin:
    """Authenticated user with a profile but 0 credits."""
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.user = User.objects.create_user(
            username='zero@test.com', email='zero@test.com', password='pass'
        )
        # Signal creates UserProfile with credits=0 — no grant_credits call needed.
        self.client.force_login(self.user)
```

### Step 3 — Migrate each view file

Order: Analyzer → Writer → Compare → Coach (most call sites last).

For each view:
1. Add `CreditCost` import at the top
2. Remove the inline `from apps.accounts.credits import deduct_credit`
3. Define the module-level `STREAM_COST` (and `PARSE_COST` for coach)
4. Replace the `if not deduct_credit(...)` branch with `if resp := COST.guard(...): return resp`
5. For coach/parse, define `_no_credits_html()` locally

### Step 4 — Write new view-level credit tests

For each tool, add to its existing `test_views.py`:

**Declaration tests (no DB):**
```python
import apps.analyzer.views as analyzer_views

def test_declared_stream_cost(self):
    self.assertEqual(analyzer_views.STREAM_COST.amount, 1)
```

**Balance-delta tests (success path):**
```python
def test_successful_stream_deducts_one_credit(self):
    grant_credits(self.user, 5, 'test setup')
    before = credit_balance(self.user)
    # ... hit the view with a valid nonce and fake service ...
    after = credit_balance(self.user)
    self.assertEqual(before - after, analyzer_views.STREAM_COST.amount)
```

**Zero-credit tests (failure path):**
```python
class StreamZeroCreditsTests(ZeroCreditsMixin, TestCase):
    def test_zero_credits_returns_sse_error(self):
        # ... hit stream view ...
        self.assertIn("credits-error", content)
        self.assertIn("event: done", content)

    def test_zero_credits_does_not_call_claude(self):
        with patch("apps.analyzer.views.get_service") as mock:
            # ... hit stream view ...
        mock.assert_not_called()
```

**Coach two-phase tests:**
```python
import apps.coach.views as coach_views

def test_declared_total_session_cost(self):
    total = coach_views.PARSE_COST.amount + coach_views.STREAM_COST.amount
    self.assertEqual(total, 2)

def test_parse_deducts_one_credit(self):
    grant_credits(self.user, 5, 'test')
    before = credit_balance(self.user)
    # ... hit parse view ...
    self.assertEqual(before - credit_balance(self.user), coach_views.PARSE_COST.amount)

def test_stream_deducts_one_credit(self):
    grant_credits(self.user, 5, 'test')
    # ... parse first to set up session ...
    before = credit_balance(self.user)
    # ... hit stream view ...
    self.assertEqual(before - credit_balance(self.user), coach_views.STREAM_COST.amount)

def test_one_credit_insufficient_after_parse(self):
    """User with exactly 1 credit can parse but not stream."""
    profile = self.user.profile
    profile.credits = 1
    profile.save(update_fields=['credits'])
    # parse succeeds ...
    # stream returns credits-error ...
```

### Step 5 — Run full suite

```bash
make test
```

All existing tests must pass. The new tests provide the only new assertions.

## What the Module Owns After This Refactor

**`CreditCost`:**
- Declares the cost at a named, importable, module-level constant
- Owns the `.deduct()` call — single import location
- Owns the `.guard()` pattern — walrus-compatible, factory-parameterized

**`credit_balance()`:**
- Read-only test primitive — one `SELECT`, no side effects
- Lives alongside `grant_credits()` so both test helpers are discoverable together

**What it does NOT own:**
- Error response construction (factories are provided by callers)
- Response protocol detection (SSE vs HTML — caller picks the factory)
- Nonce validation (stays in the view body, before the credit guard)
- Session logic

## Tests to Write (new)

| Test | Where | What it covers |
|---|---|---|
| `test_declared_stream_cost` (×4 tools) | each `test_views.py` | Cost amount without DB |
| `test_declared_total_session_cost` | `coach/test_views.py` | Two-phase sum declaration |
| `test_successful_*_deducts_one_credit` (×5) | each `test_views.py` | Balance delta on success |
| `test_zero_credits_returns_sse_error` (×4) | each stream `test_views.py` | Error path for SSE views |
| `test_zero_credits_parse_returns_402` | `coach/test_views.py` | Error path for HTML view |
| `test_zero_credits_does_not_call_*` (×5) | each `test_views.py` | No Claude call on no credits |
| `test_one_credit_insufficient_after_parse` | `coach/test_views.py` | Two-phase failure scenario |

## Tests to Keep Unchanged

All existing `test_credits.py` tests remain — they test `deduct_credit` in isolation and
are still valuable. `CreditCost.deduct()` delegates to `deduct_credit`, so those tests
remain the unit-level coverage of the atomic deduction logic.
