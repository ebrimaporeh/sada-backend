from django.contrib import admin
from .models import Donation


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ('payment_reference', 'donor_display', 'destination_display', 'destination_type', 'amount', 'fee', 'net_amount', 'provider', 'status', 'is_anonymous', 'paid_at', 'created_at')
    list_filter = ('status', 'provider', 'is_anonymous')
    search_fields = ('payment_reference', 'donor__email', 'campaign__title', 'organization__organization_name', 'phone')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'net_amount', 'donor_display', 'paid_at', 'created_at', 'updated_at')
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {'fields': ('id', 'payment_reference', 'provider_reference')}),
        ('Parties', {'fields': ('campaign', 'organization', 'donor', 'donor_display', 'is_anonymous')}),
        ('Amount', {'fields': ('amount', 'fee', 'net_amount', 'currency')}),
        ('Payment', {'fields': ('provider', 'phone', 'status')}),
        ('Message', {'fields': ('message',)}),
        ('Timestamps', {'fields': ('paid_at', 'created_at', 'updated_at')}),
    )

    def destination_display(self, obj):
        return obj.destination_title
    destination_display.short_description = 'Destination'

    def destination_type(self, obj):
        return 'Organization' if obj.is_organization_donation else 'Campaign'
    destination_type.short_description = 'Type'
