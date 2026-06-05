from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter
from pagination.base import StandardResultsPagination
from permissions.base import IsAdminUser
from .serializers import (
    CampaignListSerializer, CampaignDetailSerializer, CampaignCreateSerializer,
    CategorySerializer, CampaignUpdateCreateSerializer, CampaignUpdateSerializer,
    AdminCampaignSerializer,
)
import services.campaign_service as campaign_service


class CategoryListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='List all active categories', responses={200: CategorySerializer(many=True)})
    def get(self, request):
        categories = campaign_service.get_categories()
        serializer = CategorySerializer(categories, many=True)
        return campaign_service.success_response({'categories': serializer.data})


class CampaignListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        summary='List public campaigns',
        parameters=[
            OpenApiParameter('category', str, description='Filter by category slug'),
            OpenApiParameter('region', str, description='Filter by region'),
            OpenApiParameter('search', str, description='Search term'),
            OpenApiParameter('urgent', bool, description='Filter urgent only'),
        ],
        responses={200: CampaignListSerializer(many=True)},
    )
    def get(self, request):
        filters = {
            'category': request.query_params.get('category'),
            'region': request.query_params.get('region'),
            'search': request.query_params.get('search'),
            'urgent': request.query_params.get('urgent') == 'true',
        }
        campaigns = campaign_service.get_public_campaigns(filters)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(campaigns, request)
        serializer = CampaignListSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)


class CampaignDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='Get campaign detail by slug', responses={200: CampaignDetailSerializer})
    def get(self, request, slug):
        campaign = campaign_service.get_campaign_by_slug(slug)
        campaign_service.increment_views(campaign)
        serializer = CampaignDetailSerializer(campaign, context={'request': request})
        return campaign_service.success_response({'campaign': serializer.data})


class CampaignCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Create a new campaign', request=CampaignCreateSerializer, responses={201: CampaignDetailSerializer})
    def post(self, request):
        serializer = CampaignCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = campaign_service.create_campaign(request.user, serializer.validated_data)
        out = CampaignDetailSerializer(campaign, context={'request': request})
        return campaign_service.success_response({'campaign': out.data}, status_code=status.HTTP_201_CREATED)


class MyCampaignListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='List my campaigns', responses={200: CampaignListSerializer(many=True)})
    def get(self, request):
        campaigns = campaign_service.get_owner_campaigns(request.user)
        serializer = CampaignListSerializer(campaigns, many=True, context={'request': request})
        return campaign_service.success_response({'campaigns': serializer.data})


class MyCampaignDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Get my campaign detail', responses={200: CampaignDetailSerializer})
    def get(self, request, slug):
        campaign = campaign_service.get_owner_campaign(request.user, slug)
        serializer = CampaignDetailSerializer(campaign, context={'request': request})
        return campaign_service.success_response({'campaign': serializer.data})

    @extend_schema(summary='Update my campaign', request=CampaignCreateSerializer)
    def patch(self, request, slug):
        campaign = campaign_service.get_owner_campaign(request.user, slug)
        serializer = CampaignCreateSerializer(campaign, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = campaign_service.update_campaign(campaign, serializer.validated_data)
        out = CampaignDetailSerializer(updated, context={'request': request})
        return campaign_service.success_response({'campaign': out.data})

    @extend_schema(summary='Delete my campaign')
    def delete(self, request, slug):
        campaign = campaign_service.get_owner_campaign(request.user, slug)
        campaign_service.delete_campaign(campaign)
        return campaign_service.success_response({}, message='Campaign deleted.')


class MyCampaignTogglePauseView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Pause or resume my campaign')
    def post(self, request, slug):
        campaign = campaign_service.toggle_pause_campaign(request.user, slug)
        serializer = CampaignDetailSerializer(campaign, context={'request': request})
        return campaign_service.success_response({'campaign': serializer.data})


class MyCampaignUploadCoverView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Upload campaign cover image')
    def post(self, request, slug):
        campaign = campaign_service.get_owner_campaign(request.user, slug)
        campaign = campaign_service.upload_cover(campaign, request.FILES.get('cover_image'))
        serializer = CampaignDetailSerializer(campaign, context={'request': request})
        return campaign_service.success_response({'campaign': serializer.data})


class CampaignMediaView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Upload cover and/or gallery images for my campaign')
    def post(self, request, slug):
        campaign = campaign_service.get_owner_campaign(request.user, slug)
        cover = request.FILES.get('cover')
        gallery = request.FILES.getlist('gallery')
        campaign = campaign_service.update_campaign_media(
            campaign,
            cover_file=cover or None,
            gallery_files=gallery or None,
        )
        serializer = CampaignDetailSerializer(campaign, context={'request': request})
        return campaign_service.success_response({'campaign': serializer.data})


class CampaignGalleryImageDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Delete a gallery image from my campaign')
    def delete(self, request, slug, image_id):
        campaign = campaign_service.delete_campaign_image(request.user, slug, image_id)
        serializer = CampaignDetailSerializer(campaign, context={'request': request})
        return campaign_service.success_response({'campaign': serializer.data})


class CampaignUpdateListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Add a campaign update', request=CampaignUpdateCreateSerializer)
    def post(self, request, slug):
        campaign = campaign_service.get_owner_campaign(request.user, slug)
        serializer = CampaignUpdateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        update = campaign_service.add_campaign_update(campaign, request.user, serializer.validated_data)
        out = CampaignUpdateSerializer(update)
        return campaign_service.success_response({'update': out.data}, status_code=status.HTTP_201_CREATED)


class AdminCampaignListView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] List all campaigns', responses={200: AdminCampaignSerializer(many=True)})
    def get(self, request):
        campaigns = campaign_service.get_all_campaigns(request.query_params)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(campaigns, request)
        serializer = AdminCampaignSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminCampaignActionView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] Approve or reject a campaign')
    def post(self, request, pk, action):
        reason = request.data.get('reason', '')
        campaign = campaign_service.admin_action(pk, action, reason, request.user)
        serializer = AdminCampaignSerializer(campaign)
        return campaign_service.success_response({'campaign': serializer.data})
