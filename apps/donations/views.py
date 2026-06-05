from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema
from pagination.base import StandardResultsPagination
from permissions.base import IsAdminUser
from .serializers import DonationSerializer, DonationCreateSerializer, AdminDonationSerializer
import services.donation_service as donation_service


class DonationCreateView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='Initiate a donation', request=DonationCreateSerializer, responses={201: DonationSerializer})
    def post(self, request):
        serializer = DonationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donor = request.user if request.user.is_authenticated else None
        donation = donation_service.create_donation(donor, serializer.validated_data)
        out = DonationSerializer(donation)
        return donation_service.success_response({'donation': out.data}, status_code=status.HTTP_201_CREATED)


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


class AdminDonationListView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(summary='[Admin] List all donations', responses={200: AdminDonationSerializer(many=True)})
    def get(self, request):
        donations = donation_service.get_all_donations(request.query_params)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(donations, request)
        serializer = AdminDonationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
