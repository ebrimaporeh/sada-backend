from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter
from pagination.base import StandardResultsPagination
from permissions.base import IsAdminUser
from throttling.base import ReportCreateThrottle
from .models import Campaign, Category, CampaignReport
from .serializers import (
    CampaignListSerializer, CampaignDetailSerializer, CampaignCreateSerializer,
    CategorySerializer, CampaignUpdateCreateSerializer, CampaignUpdateSerializer,
    AdminCampaignSerializer, CampaignReportCreateSerializer, CampaignReportSerializer,
    AdminCampaignUpdateSerializer, CampaignReportUpdateSerializer,
)
import services.campaign_service as campaign_service


class CategoryListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='List all active categories', responses={200: CategorySerializer(many=True)})
    def get(self, request):
        categories = campaign_service.get_categories()
        serializer = CategorySerializer(categories, many=True, context={'request': request})
        return campaign_service.success_response({'categories': serializer.data})


class AdminCategoryDetailView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] Get category detail', responses={200: CategorySerializer})
    def get(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        serializer = CategorySerializer(category, context={'request': request})
        return campaign_service.success_response({'category': serializer.data})

    @extend_schema(
        summary='[Admin] Update category details',
        request={
            'type': 'object',
            'properties': {
                'name': {'type': 'string'},
                'description': {'type': 'string'},
            },
        }
    )
    def patch(self, request, pk):
        category = get_object_or_404(Category, pk=pk)

        if 'name' in request.data:
            category.name = request.data['name']
        if 'description' in request.data:
            category.description = request.data['description']

        category.save()
        serializer = CategorySerializer(category, context={'request': request})
        return campaign_service.success_response({'category': serializer.data})


class AdminCategoryImageUploadView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] Upload category image')
    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk)

        if 'image' not in request.FILES:
            return campaign_service.error_response('Image file is required', status_code=status.HTTP_400_BAD_REQUEST)

        image_file = request.FILES['image']
        category.image = image_file
        category.save()

        serializer = CategorySerializer(category, context={'request': request})
        return campaign_service.success_response({'category': serializer.data}, message='Image uploaded successfully')


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


class FeaturedCampaignsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='Get up to 4 featured campaigns', responses={200: CampaignListSerializer(many=True)})
    def get(self, request):
        campaigns = campaign_service.get_featured_campaigns()
        serializer = CampaignListSerializer(campaigns, many=True, context={'request': request})
        return campaign_service.success_response({'campaigns': serializer.data})


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

        images = request.FILES.getlist('images')
        update = campaign_service.add_campaign_update(
            campaign, request.user,
            title=serializer.validated_data['title'],
            content=serializer.validated_data['content'],
            images=images,
        )
        out = CampaignUpdateSerializer(update, context={'request': request})
        return campaign_service.success_response({'update': out.data}, status_code=status.HTTP_201_CREATED)


class CampaignUpdateDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Update a campaign update')
    def patch(self, request, slug, update_id):
        campaign = campaign_service.get_owner_campaign(request.user, slug)
        update = campaign_service.update_campaign_update(
            campaign, update_id, request.user,
            title=request.data.get('title'),
            content=request.data.get('content'),
            images=request.FILES.getlist('images'),
            images_to_remove=request.data.getlist('images_to_remove'),
        )
        out = CampaignUpdateSerializer(update, context={'request': request})
        return campaign_service.success_response({'update': out.data})

    @extend_schema(summary='Delete a campaign update')
    def delete(self, request, slug, update_id):
        campaign = campaign_service.get_owner_campaign(request.user, slug)
        campaign_service.delete_campaign_update(campaign, update_id, request.user)
        return campaign_service.success_response({}, message='Update deleted.')


class AdminCampaignListView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] List all campaigns', responses={200: AdminCampaignSerializer(many=True)})
    def get(self, request):
        campaigns = campaign_service.get_all_campaigns(request.query_params)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(campaigns, request)
        serializer = AdminCampaignSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)


class AdminCampaignStatsView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] Campaign stats')
    def get(self, request):
        return campaign_service.success_response(campaign_service.get_campaign_stats())


class AdminCampaignActionView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] Approve or reject a campaign')
    def post(self, request, pk, action):
        reason = request.data.get('reason', '')
        campaign = campaign_service.admin_action(pk, action, reason, request.user)
        serializer = AdminCampaignSerializer(campaign, context={'request': request})
        return campaign_service.success_response({'campaign': serializer.data})


class AdminCampaignUpdateView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] Update campaign details', request=AdminCampaignUpdateSerializer)
    def patch(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        serializer = AdminCampaignUpdateSerializer(campaign, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        out = AdminCampaignSerializer(campaign, context={'request': request})
        return campaign_service.success_response({'campaign': out.data})


class AdminCampaignDetailView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] Get campaign detail by ID', responses={200: AdminCampaignSerializer})
    def get(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        serializer = AdminCampaignSerializer(campaign, context={'request': request})
        return campaign_service.success_response({'campaign': serializer.data})


class AdminCampaignStatusChangeView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(
        summary='[Admin] Change campaign status and send email notification',
        request={
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'description': 'New campaign status'},
                'reason': {'type': 'string', 'description': 'Reason for status change (optional)'},
            },
            'required': ['status'],
        }
    )
    def post(self, request, pk):
        new_status = request.data.get('status')
        reason = request.data.get('reason', '')

        if not new_status:
            return campaign_service.error_response('Status is required')

        campaign = campaign_service.change_campaign_status(pk, new_status, reason)
        out = AdminCampaignSerializer(campaign, context={'request': request})
        return campaign_service.success_response(
            {'campaign': out.data},
            message=f'Campaign status updated to {new_status}',
            status_code=status.HTTP_200_OK
        )


class AdminCampaignMediaView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] Upload cover and gallery images for any campaign')
    def post(self, request, pk):
        campaign = get_object_or_404(Campaign, pk=pk)
        cover_file = request.FILES.get('cover')
        gallery_files = request.FILES.getlist('gallery')
        updated = campaign_service.update_campaign_media(campaign, cover_file, gallery_files)
        serializer = CampaignDetailSerializer(updated, context={'request': request})
        return campaign_service.success_response({'campaign': serializer.data})


class CampaignReportView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ReportCreateThrottle]

    @extend_schema(summary='Report a campaign', request=CampaignReportCreateSerializer)
    def post(self, request, slug):
        campaign = campaign_service.get_campaign_by_slug(slug)
        serializer = CampaignReportCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report = campaign_service.create_campaign_report(
            campaign=campaign,
            user=request.user if request.user.is_authenticated else None,
            reason=serializer.validated_data['reason'],
            description=serializer.validated_data['description'],
            reporter_name=serializer.validated_data.get('reporter_name', ''),
            reporter_phone=serializer.validated_data.get('reporter_phone', ''),
        )
        out = CampaignReportSerializer(report)
        return campaign_service.success_response(
            {'report': out.data},
            message='Thank you for reporting. Our team will review this.',
            status_code=status.HTTP_201_CREATED,
        )


class AdminCampaignReportsView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] List all campaign reports', responses={200: CampaignReportSerializer(many=True)})
    def get(self, request):
        reports = campaign_service.get_all_campaign_reports(request.query_params)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(reports, request)
        serializer = CampaignReportSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminCampaignReportStatsView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] Campaign report stats')
    def get(self, request):
        return campaign_service.success_response(campaign_service.get_campaign_report_stats())


class AdminCampaignReportUpdateView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] Update campaign report', request=CampaignReportUpdateSerializer)
    def patch(self, request, pk):
        from django.shortcuts import get_object_or_404
        report = get_object_or_404(CampaignReport, pk=pk)
        serializer = CampaignReportUpdateSerializer(report, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        out = CampaignReportSerializer(report)
        return campaign_service.success_response({'report': out.data})
