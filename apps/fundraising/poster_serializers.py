from rest_framework import serializers

import services.fundraising_destination as fundraising_destination
from .models import DestinationType, Poster, PosterImage


class PosterImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = PosterImage
        fields = ['id', 'image_url', 'created_at']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class PosterListSerializer(serializers.ModelSerializer):
    destination = serializers.SerializerMethodField()
    share_code = serializers.SerializerMethodField()

    class Meta:
        model = Poster
        fields = ['id', 'name', 'template', 'status', 'destination', 'share_code', 'created_at', 'updated_at']

    def get_destination(self, obj):
        return fundraising_destination.serialize_destination(obj, self.context.get('request'))

    def get_share_code(self, obj):
        return getattr(obj.share_link, 'code', None) if hasattr(obj, 'share_link') else None


class PosterDetailSerializer(serializers.ModelSerializer):
    destination = serializers.SerializerMethodField()
    share_code = serializers.SerializerMethodField()
    share_url = serializers.SerializerMethodField()

    class Meta:
        model = Poster
        fields = [
            'id', 'name', 'template', 'design', 'status', 'destination',
            'share_code', 'share_url', 'created_at', 'updated_at',
        ]

    def get_destination(self, obj):
        return fundraising_destination.serialize_destination(obj, self.context.get('request'))

    def get_share_code(self, obj):
        return obj.share_link.code if hasattr(obj, 'share_link') else None

    def get_share_url(self, obj):
        if not hasattr(obj, 'share_link'):
            return None
        request = self.context.get('request')
        path = f'/q/{obj.share_link.code}/'
        return request.build_absolute_uri(path) if request else path


class PosterCreateSerializer(serializers.Serializer):
    destination_type = serializers.ChoiceField(choices=DestinationType.choices)
    campaign_id = serializers.UUIDField(required=False, allow_null=True)
    organization_id = serializers.UUIDField(required=False, allow_null=True)
    name = serializers.CharField(max_length=200)
    template = serializers.ChoiceField(choices=Poster.Template.choices)
    design = serializers.JSONField(required=False)

    def validate(self, attrs):
        destination_type = attrs['destination_type']
        if destination_type == DestinationType.CAMPAIGN and not attrs.get('campaign_id'):
            raise serializers.ValidationError({'campaign_id': 'Required when destination_type is campaign.'})
        if destination_type == DestinationType.ORGANIZATION and not attrs.get('organization_id'):
            raise serializers.ValidationError({'organization_id': 'Required when destination_type is organization.'})
        return attrs


class PosterUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    design = serializers.JSONField(required=False)
    status = serializers.ChoiceField(choices=Poster.Status.choices, required=False)
    # Lets the editor's mid-edit size selector (PosterEditor.jsx ->
    # ElementsPanel.jsx) keep this in sync with the regenerated
    # design.width/height it sends alongside it -- template is otherwise
    # only set once at creation (PosterCreateSerializer).
    template = serializers.ChoiceField(choices=Poster.Template.choices, required=False)
