from django.contrib import admin

from .models import Embed, Poster, PosterImage, ShareLink


def _destination_display(obj):
    if obj.destination_type == obj.DestinationType.CAMPAIGN:
        return f'Campaign: {obj.campaign.title}' if obj.campaign_id else 'Campaign: (missing)'
    return f'Organization: {obj.organization.organization_name}' if obj.organization_id else 'Organization: (missing)'


class PosterImageInline(admin.TabularInline):
    model = PosterImage
    extra = 0
    readonly_fields = ('image', 'created_at')


@admin.register(Poster)
class PosterAdmin(admin.ModelAdmin):
    list_display = ('name', 'destination', 'template', 'status', 'created_at', 'updated_at')
    list_filter = ('destination_type', 'template', 'status')
    search_fields = ('name', 'campaign__title', 'organization__organization_name')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [PosterImageInline]

    @admin.display(description='Destination')
    def destination(self, obj):
        return _destination_display(obj)


@admin.register(Embed)
class EmbedAdmin(admin.ModelAdmin):
    list_display = ('name', 'destination', 'layout', 'is_active', 'created_at', 'updated_at')
    list_filter = ('destination_type', 'layout', 'is_active')
    search_fields = ('name', 'campaign__title', 'organization__organization_name')
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Destination')
    def destination(self, obj):
        return _destination_display(obj)


@admin.register(ShareLink)
class ShareLinkAdmin(admin.ModelAdmin):
    list_display = ('code', 'poster', 'click_count', 'created_at')
    readonly_fields = ('code', 'click_count', 'created_at', 'updated_at')
    search_fields = ('code', 'poster__name')
