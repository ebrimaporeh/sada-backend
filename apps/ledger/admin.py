from django.contrib import admin
from .models import Account, Transaction, LedgerEntry


class ReadOnlyAdmin(admin.ModelAdmin):
    """The ledger has no add/edit/delete UI by design (see models.py's
    ImmutableModel) -- Django admin here is strictly a way to look at the
    data, not manage it."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class LedgerEntryInline(admin.TabularInline):
    model = LedgerEntry
    extra = 0
    fields = ('account', 'direction', 'amount', 'currency', 'created_at')
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Account)
class AccountAdmin(ReadOnlyAdmin):
    list_display = ('code', 'type', 'owner_type', 'owner_id', 'currency', 'created_at')
    list_filter = ('type', 'currency')
    search_fields = ('code', 'owner_id', 'name')


@admin.register(Transaction)
class TransactionAdmin(ReadOnlyAdmin):
    list_display = ('id', 'entry_type', 'description', 'source_type', 'source_id', 'reverses', 'created_at')
    list_filter = ('entry_type',)
    search_fields = ('description', 'source_id', 'idempotency_key')
    inlines = [LedgerEntryInline]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ReadOnlyAdmin):
    list_display = ('id', 'transaction', 'account', 'direction', 'amount', 'currency', 'created_at')
    list_filter = ('direction', 'currency')
    search_fields = ('account__code',)
