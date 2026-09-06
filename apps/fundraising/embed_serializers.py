from rest_framework import serializers

import services.fundraising_destination as fundraising_destination
from .models import DestinationType, Embed


class EmbedListSerializer(serializers.ModelSerializer):
    destination = serializers.SerializerMethodField()

    class Meta:
        model = Embed
        fields = ['id', 'name', 'layout', 'is_active', 'destination', 'created_at', 'updated_at']

    def get_destination(self, obj):
        return fundraising_destination.serialize_destination(obj, self.context.get('request'))


class EmbedDetailSerializer(serializers.ModelSerializer):
    destination = serializers.SerializerMethodField()
    embed_url = serializers.SerializerMethodField()

    class Meta:
        model = Embed
        fields = [
            'id', 'name', 'layout', 'configuration', 'is_active', 'destination',
            'embed_url', 'created_at', 'updated_at',
        ]

    def get_destination(self, obj):
        return fundraising_destination.serialize_destination(obj, self.context.get('request'))

    def get_embed_url(self, obj):
        from django.conf import settings
        base = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
        return f'{base}/embed/{obj.id}'


class EmbedPublicSerializer(serializers.ModelSerializer):
    """Backs GET /fundraising/embeds/<id>/public/ -- deliberately lean.
    Never exposes campaign/organization internal ids beyond the embed's own
    public uuid, never financial detail beyond what the destination's own
    public pages already show (progress/goal/raised), never anything
    authenticated-only."""
    destination = serializers.SerializerMethodField()

    class Meta:
        model = Embed
        fields = ['id', 'name', 'layout', 'configuration', 'is_active', 'destination']

    def get_destination(self, obj):
        return fundraising_destination.serialize_destination(obj, self.context.get('request'))


class EmbedCreateSerializer(serializers.Serializer):
    destination_type = serializers.ChoiceField(choices=DestinationType.choices)
    campaign_id = serializers.UUIDField(required=False, allow_null=True)
    organization_id = serializers.UUIDField(required=False, allow_null=True)
    name = serializers.CharField(max_length=200)
    layout = serializers.ChoiceField(choices=Embed.Layout.choices, required=False)
    configuration = serializers.JSONField(required=False)

    def validate(self, attrs):
        destination_type = attrs['destination_type']
        if destination_type == DestinationType.CAMPAIGN and not attrs.get('campaign_id'):
            raise serializers.ValidationError({'campaign_id': 'Required when destination_type is campaign.'})
        if destination_type == DestinationType.ORGANIZATION and not attrs.get('organization_id'):
            raise serializers.ValidationError({'organization_id': 'Required when destination_type is organization.'})
        return attrs


class EmbedUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    layout = serializers.ChoiceField(choices=Embed.Layout.choices, required=False)
    configuration = serializers.JSONField(required=False)
