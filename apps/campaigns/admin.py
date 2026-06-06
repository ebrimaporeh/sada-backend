from django.contrib import admin
from .models import Category, Campaign, CampaignImage, CampaignUpdate


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'icon', 'is_active', 'campaign_count')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ('id', 'created_at', 'updated_at')

    def campaign_count(self, obj):
        return obj.campaigns.count()
    campaign_count.short_description = 'Campaigns'


class CampaignImageInline(admin.TabularInline):
    model = CampaignImage
    extra = 0
    readonly_fields = ('id',)
    fields = ('image', 'order', 'is_cover')


class CampaignUpdateInline(admin.TabularInline):
    model = CampaignUpdate
    extra = 0
    readonly_fields = ('id', 'created_at')
    fields = ('title', 'content', 'posted_by', 'created_at')


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'category', 'status', 'region', 'raised', 'goal', 'progress_percent', 'donors_count', 'is_urgent', 'is_featured', 'created_at')
    list_filter = ('status', 'region', 'category', 'is_urgent', 'is_featured', 'is_anonymous')
    search_fields = ('title', 'slug', 'owner__email', 'beneficiary')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'slug', 'progress_percent', 'raised', 'donors_count', 'views_count', 'approved_at', 'completed_at', 'created_at', 'updated_at')
    inlines = [CampaignImageInline, CampaignUpdateInline]
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {'fields': ('id', 'slug', 'owner', 'category', 'status')}),
        ('Content', {'fields': ('title', 'short_description', 'story', 'cover_image')}),
        ('Beneficiary', {'fields': ('beneficiary', 'beneficiary_relationship', 'is_anonymous')}),
        ('Fundraising', {'fields': ('goal', 'raised', 'currency', 'deadline', 'donors_count', 'views_count', 'progress_percent')}),
        ('Location', {'fields': ('region',)}),
        ('Flags', {'fields': ('is_urgent', 'is_featured')}),
        ('Review', {'fields': ('rejection_reason', 'approved_at', 'completed_at')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

    actions = ['approve_campaigns', 'suspend_campaigns']

    def approve_campaigns(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status__in=['pending', 'draft']).update(
            status='active', approved_at=timezone.now()
        )
        self.message_user(request, f'{updated} campaign(s) approved.')
    approve_campaigns.short_description = 'Approve selected campaigns'

    def suspend_campaigns(self, request, queryset):
        updated = queryset.exclude(status='suspended').update(status='suspended')
        self.message_user(request, f'{updated} campaign(s) suspended.')
    suspend_campaigns.short_description = 'Suspend selected campaigns'
