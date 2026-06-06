from django.contrib import admin
from .models import Payment, Payout


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'donation', 'provider', 'amount', 'status', 'completed_at', 'created_at')
    list_filter = ('status', 'provider')
    search_fields = ('reference', 'provider_reference', 'donation__campaign__title')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'completed_at', 'created_at', 'updated_at')

    fieldsets = (
        (None, {'fields': ('id', 'reference', 'provider_reference')}),
        ('Linked Donation', {'fields': ('donation',)}),
        ('Payment Details', {'fields': ('provider', 'amount', 'currency', 'status')}),
        ('Raw Response', {'fields': ('raw_response',), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('completed_at', 'created_at', 'updated_at')}),
    )


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ('reference', 'campaign', 'requested_by', 'amount', 'fee', 'net_amount', 'provider', 'phone', 'status', 'processed_at', 'created_at')
    list_filter = ('status', 'provider')
    search_fields = ('reference', 'campaign__title', 'requested_by__email', 'phone')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'processed_at', 'created_at', 'updated_at')

    fieldsets = (
        (None, {'fields': ('id', 'reference', 'provider_reference')}),
        ('Parties', {'fields': ('campaign', 'requested_by')}),
        ('Amount', {'fields': ('amount', 'fee', 'net_amount', 'currency')}),
        ('Payment', {'fields': ('provider', 'phone', 'status')}),
        ('Notes', {'fields': ('notes',)}),
        ('Timestamps', {'fields': ('processed_at', 'created_at', 'updated_at')}),
    )

    actions = ['mark_completed', 'mark_failed']

    def mark_completed(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status__in=['pending', 'processing']).update(
            status='completed', processed_at=timezone.now()
        )
        self.message_user(request, f'{updated} payout(s) marked as completed.')
    mark_completed.short_description = 'Mark selected payouts as completed'

    def mark_failed(self, request, queryset):
        updated = queryset.exclude(status='failed').update(status='failed')
        self.message_user(request, f'{updated} payout(s) marked as failed.')
    mark_failed.short_description = 'Mark selected payouts as failed'
