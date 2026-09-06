from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.campaigns.models import Campaign
from apps.users.models import Organization
from pagination.base import StandardResultsPagination
import services.embed_service as embed_service
from .models import DestinationType
from .embed_serializers import (
    EmbedCreateSerializer, EmbedDetailSerializer, EmbedListSerializer, EmbedPublicSerializer, EmbedUpdateSerializer,
)


def _resolve_destination_objects(validated_data):
    campaign = None
    organization = None
    if validated_data['destination_type'] == DestinationType.CAMPAIGN:
        campaign = get_object_or_404(Campaign, pk=validated_data['campaign_id'])
    else:
        organization = get_object_or_404(Organization, pk=validated_data['organization_id'])
    return campaign, organization


@extend_schema(tags=['Fundraising'], summary='List my embeds / create an embed')
class EmbedListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        embeds = embed_service.get_owner_embeds(request.user)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(embeds, request)
        serializer = EmbedListSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = EmbedCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        campaign, organization = _resolve_destination_objects(data)
        embed = embed_service.create_embed(
            request.user, destination_type=data['destination_type'], campaign=campaign, organization=organization,
            name=data['name'], layout=data.get('layout'), configuration=data.get('configuration'),
        )
        out = EmbedDetailSerializer(embed, context={'request': request})
        return Response({'success': True, 'message': 'Embed created.', 'data': {'embed': out.data}}, status=201)


@extend_schema(tags=['Fundraising'], summary='Retrieve / update / delete an embed')
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

    def delete(self, request, pk):
        embed = embed_service.get_owner_embed(request.user, pk)
        embed_service.delete_embed(request.user, embed)
        return Response({'success': True, 'message': 'Embed deleted.'}, status=204)


@extend_schema(tags=['Fundraising'], summary='Duplicate an embed')
class EmbedDuplicateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        embed = embed_service.get_owner_embed(request.user, pk)
        new_embed = embed_service.duplicate_embed(request.user, embed)
        out = EmbedDetailSerializer(new_embed, context={'request': request})
        return Response({'success': True, 'message': 'Embed duplicated.', 'data': {'embed': out.data}}, status=201)


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
