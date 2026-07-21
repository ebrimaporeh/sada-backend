from rest_framework import serializers
from .models import VisionTopic


class VisionTopicListSerializer(serializers.ModelSerializer):
    """Lean projection for the public index page -- title/summary/slug
    only, same reasoning as AdminCampaignListSerializer: don't serialize
    four markdown documents' worth of content for every topic just to
    render a list of teasers."""
    class Meta:
        model = VisionTopic
        fields = ['slug', 'title', 'summary', 'order']


class VisionTopicDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisionTopic
        fields = [
            'slug', 'title', 'summary', 'order',
            'current_state', 'implementation', 'short_term_vision', 'long_term_vision',
            'updated_at',
        ]


class AdminVisionTopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisionTopic
        fields = [
            'id', 'slug', 'title', 'summary', 'order', 'is_published',
            'current_state', 'implementation', 'short_term_vision', 'long_term_vision',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_slug(self, value):
        # Model.save() auto-generates one if blank -- but if an admin does
        # supply a slug explicitly, it has to actually look like a slug
        # (this is a URL path segment, not free text).
        from django.utils.text import slugify
        if value and slugify(value) != value:
            raise serializers.ValidationError('Use lowercase letters, numbers, and hyphens only.')
        return value
