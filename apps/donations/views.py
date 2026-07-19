from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema
from pagination.base import StandardResultsPagination
from permissions.base import HasResourceAccess
from permissions.roles import Resource
from throttling.base import DonationCreateThrottle
from .serializers import DonationSerializer, DonationCreateSerializer, AdminDonationSerializer, AdminDonationUpdateSerializer
import services.donation_service as donation_service


class DonationCreateView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [DonationCreateThrottle]

    @extend_schema(summary='Initiate a donation', request=DonationCreateSerializer, responses={201: DonationSerializer})
    def post(self, request):
        serializer = DonationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donor = request.user if request.user.is_authenticated else None
        donation, payment_link = donation_service.create_donation(donor, serializer.validated_data)
        out = DonationSerializer(donation)
        if payment_link is None:
            return donation_service.error_response(
                'Could not start payment. Please try again.',
                status_code=status.HTTP_502_BAD_GATEWAY,
            )
        return donation_service.success_response(
            {'donation': out.data, 'payment_link': payment_link},
            status_code=status.HTTP_201_CREATED,
        )


class DonationVerifyView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='Reconcile a donation status directly with ModemPay', responses={200: DonationSerializer})
    def get(self, request, reference):
        donation = donation_service.reconcile_donation_by_reference(reference)
        if donation is None:
            return donation_service.error_response('Donation not found.', status_code=status.HTTP_404_NOT_FOUND)
        out = DonationSerializer(donation)
        return donation_service.success_response({'donation': out.data})


class MyDonationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='List my donations', responses={200: DonationSerializer(many=True)})
    def get(self, request):
        donations = donation_service.get_user_donations(request.user)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(donations, request)
        serializer = DonationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class CampaignDonorListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='List donors for my campaign', responses={200: DonationSerializer(many=True)})
    def get(self, request, slug):
        donations = donation_service.get_campaign_donors(request.user, slug)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(donations, request)
        serializer = DonationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class PublicCampaignDonorListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='List donors for a public campaign page', responses={200: DonationSerializer(many=True)})
    def get(self, request, slug):
        donations = donation_service.get_public_campaign_donors(slug)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(donations, request)
        serializer = DonationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminDonationListView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.DONATIONS

    @extend_schema(summary='[Admin] List all donations', responses={200: AdminDonationSerializer(many=True)})
    def get(self, request):
        donations = donation_service.get_all_donations(request.query_params)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(donations, request)
        serializer = AdminDonationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminDonationStatsView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.DONATIONS

    @extend_schema(summary='[Admin] Donation stats')
    def get(self, request):
        return donation_service.success_response(donation_service.get_donation_stats())


class AdminDonationUpdateView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.DONATIONS

    @extend_schema(summary='[Admin] Update donation details', request=AdminDonationUpdateSerializer)
    def patch(self, request, pk):
        from django.shortcuts import get_object_or_404
        from .models import Donation
        donation = get_object_or_404(Donation, pk=pk)
        serializer = AdminDonationUpdateSerializer(donation, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        donation = donation_service.admin_update_donation(donation, serializer.validated_data)
        out = AdminDonationSerializer(donation)
        return donation_service.success_response({'donation': out.data})
