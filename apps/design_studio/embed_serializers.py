from dataclasses import asdict

from rest_framework import serializers

import services.design_studio_destination as design_studio_destination
from .models import Embed


def _serialize_organization(organization, request=None) -> dict:
    """Lean organization projection shared by both serializers below --
    deliberately not the full OrganizationSerializer (this is public-facing
    on EmbedPublicSerializer, same "never expose more than the destination's
    own public pages already show" rule as design_studio_destination's own
    docstring)."""
    logo_url = None
    if organization.logo:
        logo_url = request.build_absolute_uri(organization.logo.url) if request is not None else organization.logo.url
    return {
        'id': str(organization.id),
        'organization_name': organization.organization_name,
        'slug': organization.slug,
        'logo_url': logo_url,
    }


class EmbedDetailSerializer(serializers.ModelSerializer):
    """Authenticated, Studio-facing shape. `destinations` carries the exact
    same gallery the public widget renders, computed the same way, so the
    Studio's live preview (EmbedPreview.jsx) can render real data without a
    second round-trip through the public/AllowAny endpoint."""
    organization = serializers.SerializerMethodField()
    destinations = serializers.SerializerMethodField()
    embed_url = serializers.SerializerMethodField()

    class Meta:
        model = Embed
        fields = [
            'id', 'name', 'layout', 'configuration', 'is_active', 'organization', 'destinations',
            'embed_url', 'return_url', 'created_at', 'updated_at',
        ]

    def get_organization(self, obj):
        return _serialize_organization(obj.organization, self.context.get('request'))

    def get_destinations(self, obj):
        request = self.context.get('request')
        return [
            asdict(d) for d in design_studio_destination.resolve_embed_gallery_destinations(obj.organization, request=request)
        ]

    def get_embed_url(self, obj):
        from django.conf import settings
        base = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
        return f'{base}/embed/{obj.id}'


class EmbedPublicSerializer(serializers.ModelSerializer):
    """Backs GET /design-studio/embeds/<id>/public/ -- deliberately lean.
    Never exposes anything beyond the embed's own public uuid, the
    organization's public projection, and each destination's own public
    fields (progress/goal/raised etc., same as their standalone public
    pages already show) -- never anything authenticated-only.

    `layout` is a SerializerMethodField (not a plain passthrough) so a
    `?layout=` query param on this endpoint can override the embed's own
    stored default for this one render -- see EmbedPublicView. This is what
    lets one embed be installed multiple times across a site with a
    different layout at each spot, all sharing the same underlying
    destinations/appearance/donation-flow config, rather than needing a
    separate Embed per placement."""
    organization = serializers.SerializerMethodField()
    destinations = serializers.SerializerMethodField()
    layout = serializers.SerializerMethodField()

    class Meta:
        model = Embed
        fields = ['id', 'name', 'layout', 'configuration', 'is_active', 'organization', 'destinations']

    def get_organization(self, obj):
        return _serialize_organization(obj.organization, self.context.get('request'))

    def get_destinations(self, obj):
        request = self.context.get('request')
        return [
            asdict(d) for d in design_studio_destination.resolve_embed_gallery_destinations(obj.organization, request=request)
        ]

    def get_layout(self, obj):
        return self.context.get('layout_override') or obj.layout


class EmbedUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    layout = serializers.ChoiceField(choices=Embed.Layout.choices, required=False)
    configuration = serializers.JSONField(required=False)
    # `required=True` here doesn't force every PATCH to include it --
    # EmbedDetailView.patch always instantiates this with partial=True, and
    # DRF skips the required check entirely for a key that's simply absent
    # from a partial update. It only takes effect if return_url IS included
    # in the request: then it can't be blank, same as at creation.
    return_url = serializers.URLField(required=True)
