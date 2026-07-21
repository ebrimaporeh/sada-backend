from django.contrib import admin
from .models import VisionTopic


@admin.register(VisionTopic)
class VisionTopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'order', 'is_published', 'updated_at')
    list_filter = ('is_published',)
    search_fields = ('title', 'slug', 'summary')
    prepopulated_fields = {'slug': ('title',)}
