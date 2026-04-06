from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    credits = models.IntegerField(default=0)

    def __str__(self):
        return f"Profile({self.user.email}, {self.credits} credits)"


class CreditTransaction(models.Model):
    class TxType(models.TextChoices):
        SIGNUP_BONUS = 'signup_bonus', 'Signup Bonus'
        PURCHASE = 'purchase', 'Purchase'
        USAGE = 'usage', 'Usage'
        REFUND = 'refund', 'Refund'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='credit_transactions',
    )
    amount = models.IntegerField()  # positive = grant, negative = usage
    description = models.CharField(max_length=255)
    tx_type = models.CharField(max_length=20, choices=TxType.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    lemon_order_id = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'created_at'])]

    def __str__(self):
        return f"{self.user.email} {self.amount:+d} ({self.tx_type})"
