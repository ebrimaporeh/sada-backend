from rest_framework import serializers
from .models import Event


class TrackEventSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=Event.Type.choices)
    campaign_slug = serializers.SlugField(required=False, allow_blank=True)
    session_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
    metadata = serializers.JSONField(required=False)
