from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.views import View
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.campaigns.models import Campaign
from apps.users.models import Organization
from pagination.base import StandardResultsPagination
import services.poster_service as poster_service
from .models import DestinationType
from .poster_serializers import (
    PosterCreateSerializer, PosterDetailSerializer, PosterImageSerializer, PosterListSerializer, PosterUpdateSerializer,
)


def _resolve_destination_objects(validated_data):
    """Turns the create serializer's campaign_id/organization_id into real
    instances -- 404s (not a validation error) for an id that doesn't
    exist, same as every other "fetch by id" endpoint in this codebase."""
    campaign = None
    organization = None
    if validated_data['destination_type'] == DestinationType.CAMPAIGN:
        campaign = get_object_or_404(Campaign, pk=validated_data['campaign_id'])
    else:
        organization = get_object_or_404(Organization, pk=validated_data['organization_id'])
    return campaign, organization


@extend_schema(tags=['Fundraising'], summary='List my posters / create a poster')
class PosterListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        posters = poster_service.get_owner_posters(request.user)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(posters, request)
        serializer = PosterListSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = PosterCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        campaign, organization = _resolve_destination_objects(data)
        poster = poster_service.create_poster(
            request.user, destination_type=data['destination_type'], campaign=campaign, organization=organization,
            name=data['name'], template=data['template'], design=data.get('design'),
        )
        out = PosterDetailSerializer(poster, context={'request': request})
        return Response({'success': True, 'message': 'Poster created.', 'data': {'poster': out.data}}, status=201)


@extend_schema(tags=['Fundraising'], summary='Retrieve / update / delete a poster')
class PosterDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        poster = poster_service.get_owner_poster(request.user, pk)
        out = PosterDetailSerializer(poster, context={'request': request})
        return Response({'success': True, 'data': {'poster': out.data}})

    def patch(self, request, pk):
        poster = poster_service.get_owner_poster(request.user, pk)
        serializer = PosterUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        poster = poster_service.update_poster(request.user, poster, **serializer.validated_data)
        out = PosterDetailSerializer(poster, context={'request': request})
        return Response({'success': True, 'message': 'Poster saved.', 'data': {'poster': out.data}})

    def delete(self, request, pk):
        poster = poster_service.get_owner_poster(request.user, pk)
        poster_service.delete_poster(request.user, poster)
        return Response({'success': True, 'message': 'Poster deleted.'}, status=204)


@extend_schema(tags=['Fundraising'], summary='Duplicate a poster')
class PosterDuplicateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        poster = poster_service.get_owner_poster(request.user, pk)
        new_poster = poster_service.duplicate_poster(request.user, poster)
        out = PosterDetailSerializer(new_poster, context={'request': request})
        return Response({'success': True, 'message': 'Poster duplicated.', 'data': {'poster': out.data}}, status=201)


@extend_schema(tags=['Fundraising'], summary='Upload an image for use in a poster design')
class PosterImageUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        poster = poster_service.get_owner_poster(request.user, pk)
        image = poster_service.upload_poster_image(request.user, poster, request.FILES.get('image'))
        out = PosterImageSerializer(image, context={'request': request})
        return Response({'success': True, 'message': 'Image uploaded.', 'data': {'image': out.data}}, status=201)


class ShareLinkRedirectView(View):
    """Backs /q/<code>/ -- the durable QR/print target for a poster. Root-
    mounted (not under /api/v1/...), same mounting style as apps.seo's
    /share/... preview pages, since this is meant to be scanned/typed by a
    person, not called by the SPA."""
    def get(self, request, code):
        public_url = poster_service.resolve_share_link(code)
        return HttpResponseRedirect(public_url)
