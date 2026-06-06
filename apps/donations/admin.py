from django.contrib import admin
from .models import Donation


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ('payment_reference', 'donor_display', 'campaign', 'amount', 'fee', 'net_amount', 'provider', 'status', 'is_anonymous', 'paid_at', 'created_at')
    list_filter = ('status', 'provider', 'is_anonymous')
    search_fields = ('payment_reference', 'donor__email', 'campaign__title', 'phone')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'net_amount', 'donor_display', 'paid_at', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {'fields': ('id', 'payment_reference', 'provider_reference')}),
        ('Parties', {'fields': ('campaign', 'donor', 'donor_display', 'is_anonymous')}),
        ('Amount', {'fields': ('amount', 'fee', 'net_amount', 'currency')}),
        ('Payment', {'fields': ('provider', 'phone', 'status')}),
        ('Message', {'fields': ('message',)}),
        ('Timestamps', {'fields': ('paid_at', 'created_at', 'updated_at')}),
    )
