from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'title', 'is_read', 'read_at', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('user__email', 'title', 'message')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'read_at', 'created_at', 'updated_at')

    fieldsets = (
        (None, {'fields': ('id', 'user', 'notification_type')}),
        ('Content', {'fields': ('title', 'message', 'link')}),
        ('Status', {'fields': ('is_read', 'read_at')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

    actions = ['mark_read', 'mark_unread']

    def mark_read(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(is_read=False).update(is_read=True, read_at=timezone.now())
        self.message_user(request, f'{updated} notification(s) marked as read.')
    mark_read.short_description = 'Mark selected notifications as read'

    def mark_unread(self, request, queryset):
        updated = queryset.filter(is_read=True).update(is_read=False, read_at=None)
        self.message_user(request, f'{updated} notification(s) marked as unread.')
    mark_unread.short_description = 'Mark selected notifications as unread'
