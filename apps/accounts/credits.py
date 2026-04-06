from django.db import transaction

from .models import CreditTransaction, UserProfile


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
