from django.contrib import admin

from .models import CreditTransaction, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'credits')
    search_fields = ('user__email',)


@admin.register(CreditTransaction)
class CreditTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'tx_type', 'description', 'created_at')
    list_filter = ('tx_type',)
    search_fields = ('user__email', 'lemon_order_id')
    readonly_fields = ('created_at',)
