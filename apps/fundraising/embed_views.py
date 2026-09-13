from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import services.embed_service as embed_service
from .embed_serializers import EmbedDetailSerializer, EmbedPublicSerializer, EmbedUpdateSerializer


@extend_schema(tags=['Fundraising'], summary="Get (or create) my organization's embed")
class OrganizationEmbedView(APIView):
    """The only way to reach an Embed as its owner -- there's no separate
    create endpoint. GET always succeeds for any organization the caller
    can manage, creating a blank embed on first visit (see
    embed_service.get_or_create_org_embed)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, organization_id):
        embed = embed_service.get_owner_org_embed(request.user, organization_id)
        out = EmbedDetailSerializer(embed, context={'request': request})
        return Response({'success': True, 'data': {'embed': out.data}})


@extend_schema(tags=['Fundraising'], summary='Update an embed')
class EmbedDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        embed = embed_service.get_owner_embed(request.user, pk)
        out = EmbedDetailSerializer(embed, context={'request': request})
        return Response({'success': True, 'data': {'embed': out.data}})

    def patch(self, request, pk):
        embed = embed_service.get_owner_embed(request.user, pk)
        serializer = EmbedUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        embed = embed_service.update_embed(request.user, embed, **serializer.validated_data)
        out = EmbedDetailSerializer(embed, context={'request': request})
        return Response({'success': True, 'message': 'Embed saved.', 'data': {'embed': out.data}})


@extend_schema(tags=['Fundraising'], summary='Activate an embed')
class EmbedActivateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        embed = embed_service.get_owner_embed(request.user, pk)
        embed = embed_service.set_embed_active(request.user, embed, True)
        out = EmbedDetailSerializer(embed, context={'request': request})
        return Response({'success': True, 'message': 'Embed activated.', 'data': {'embed': out.data}})


@extend_schema(tags=['Fundraising'], summary='Deactivate an embed')
class EmbedDeactivateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        embed = embed_service.get_owner_embed(request.user, pk)
        embed = embed_service.set_embed_active(request.user, embed, False)
        out = EmbedDetailSerializer(embed, context={'request': request})
        return Response({'success': True, 'message': 'Embed deactivated.', 'data': {'embed': out.data}})


@extend_schema(
    tags=['Fundraising'], summary='Get an embed for public rendering (no auth required)',
    responses={200: EmbedPublicSerializer},
)
class EmbedPublicView(APIView):
    """Backs the public /embed/<id> widget -- deliberately AllowAny and
    lean, see EmbedPublicSerializer's docstring. Renders even when
    is_active is False so the widget can show an explicit inactive state
    instead of a broken/blank iframe on a site that already installed it."""
    permission_classes = [AllowAny]

    def get(self, request, pk):
        embed = embed_service.get_public_embed(pk)
        out = EmbedPublicSerializer(embed, context={'request': request})
        return Response({'success': True, 'data': {'embed': out.data}})
