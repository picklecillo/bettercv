from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from .models import CreditTransaction, UserProfile

if TYPE_CHECKING:
    from django.http import HttpResponse, StreamingHttpResponse


def deduct_credit(user, amount: int = 1, description: str = 'Tool usage') -> bool:
    """
    Atomically deduct `amount` credits from `user`.
    Returns True on success, False if the user has insufficient credits.
    Uses select_for_update() to prevent concurrent double-spend.
    """
    with transaction.atomic():
        try:
            profile = UserProfile.objects.select_for_update().get(user=user)
        except UserProfile.DoesNotExist:
            return False
        if profile.credits < amount:
            return False
        profile.credits -= amount
        profile.save(update_fields=['credits'])
        CreditTransaction.objects.create(
            user=user,
            amount=-amount,
            description=description,
            tx_type=CreditTransaction.TxType.USAGE,
        )
    return True


def grant_credits(
    user,
    amount: int,
    description: str,
    tx_type: str = CreditTransaction.TxType.PURCHASE,
    lemon_order_id: str = '',
) -> None:
    """Grant `amount` credits to `user`. Always succeeds."""
    with transaction.atomic():
        profile, _ = UserProfile.objects.select_for_update().get_or_create(user=user)
        profile.credits += amount
        profile.save(update_fields=['credits'])
        CreditTransaction.objects.create(
            user=user,
            amount=amount,
            description=description,
            tx_type=tx_type,
            lemon_order_id=lemon_order_id,
        )


def check_credits(user, amount: int = 1) -> bool:
    """Non-locking credit balance check. Use as a fast-path guard."""
    try:
        return UserProfile.objects.get(user=user).credits >= amount
    except UserProfile.DoesNotExist:
        return False


def credit_balance(user) -> int:
    """
    Return the current credit balance for user.

    Intended for test post-condition assertions only. Never use in production
    view logic — use check_credits() there (non-locking fast-path).
    """
    try:
        return UserProfile.objects.get(user=user).credits
    except UserProfile.DoesNotExist:
        return 0


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

    def deduct(self, user) -> bool:
        """Atomically deduct. Returns True on success, False if insufficient."""
        return deduct_credit(user, self.amount, self.description)

    def guard(
        self,
        user,
        on_insufficient: Callable[[], HttpResponse | StreamingHttpResponse],
    ) -> HttpResponse | StreamingHttpResponse | None:
        """
        Deduct credits or return the appropriate error response.

        Returns None on success — caller continues normally.
        Returns on_insufficient() if the user has insufficient credits.
        """
        if not self.deduct(user):
            return on_insufficient()
        return None
