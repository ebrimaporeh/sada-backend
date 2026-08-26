from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter
from pagination.base import StandardResultsPagination
from permissions.base import HasResourceAccess
from permissions.roles import Resource
from throttling.base import DonationCreateThrottle
from .serializers import (
    DonationSerializer, DonationCreateSerializer, AdminDonationSerializer,
    AdminDonationUpdateSerializer, AdminDonationRefundSerializer,
)
import services.donation_service as donation_service
import services.audit_service as audit_service
import services.events_service as events_service
import services.consent_service as consent_service
from apps.audit.models import AuditLog
from apps.events.models import Event


class DonationCreateView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [DonationCreateThrottle]

    @extend_schema(summary='Initiate a donation', request=DonationCreateSerializer, responses={201: DonationSerializer})
    def post(self, request):
        serializer = DonationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donor = request.user if request.user.is_authenticated else None
        donation, payment_link, error_message = donation_service.create_donation(donor, serializer.validated_data)
        out = DonationSerializer(donation)

        # A real Donation row was persisted either way (even a gateway
        # failure still creates one, marked FAILED) -- that's the state
        # change worth an audit entry, regardless of what happens next.
        # A guest donor is still a real person, not "the system" -- use
        # whatever name they gave rather than leaving actor/actor_name
        # blank (which would fall back to a bare "System" in the UI). This
        # deliberately ignores the donation's own is_anonymous flag, which
        # only controls *public* display -- admins reading the audit log
        # should still see who actually donated.
        actor_name = donor.full_name if donor else (donation.donor_name or 'Anonymous donor')
        audit_service.log(
            donor, AuditLog.Action.DONATION_CREATED, donation,
            f'{actor_name} donated D{donation.amount} to "{donation.campaign.title}"',
            actor_name=actor_name,
        )

        if payment_link is None:
            # A specific error_message means the gateway rejected something
            # the donor can actually fix (e.g. amount over its limit) --
            # tell them what it was instead of a generic "try again" that
            # would just fail identically on retry. No message means a
            # genuine gateway/network failure, kept as 502.
            if error_message:
                return donation_service.error_response(error_message, status_code=status.HTTP_400_BAD_REQUEST)
            return donation_service.error_response(
                'Could not start payment. Please try again.',
                status_code=status.HTTP_502_BAD_GATEWAY,
            )

        events_service.track(
            Event.Type.DONATION_STARTED, user=donor, campaign=donation.campaign,
            metadata={'amount': str(donation.amount), 'provider': donation.provider},
            ip_address=consent_service.get_client_ip(request) or None,
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

    @extend_schema(
        summary='List donors for a public campaign page',
        parameters=[OpenApiParameter('sort', str, description='latest (default) or highest')],
        responses={200: DonationSerializer(many=True)},
    )
    def get(self, request, slug):
        sort = request.query_params.get('sort', 'latest')
        donations = donation_service.get_public_campaign_donors(slug, sort=sort)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(donations, request)
        serializer = DonationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminDonationListView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.DONATIONS_VIEW

    @extend_schema(summary='[Admin] List all donations', responses={200: AdminDonationSerializer(many=True)})
    def get(self, request):
        donations = donation_service.get_all_donations(request.query_params)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(donations, request)
        serializer = AdminDonationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminDonationStatsView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.DONATIONS_VIEW

    @extend_schema(summary='[Admin] Donation stats')
    def get(self, request):
        return donation_service.success_response(donation_service.get_donation_stats())


class AdminDonationUpdateView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.DONATIONS_EDIT

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


class AdminDonationRefundView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.DONATIONS_EDIT

    @extend_schema(summary='[Admin] Refund a paid donation', request=AdminDonationRefundSerializer)
    def post(self, request, pk):
        from django.shortcuts import get_object_or_404
        from .models import Donation
        donation = get_object_or_404(Donation, pk=pk)
        serializer = AdminDonationRefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        donation = donation_service.refund_donation(donation, reason=serializer.validated_data['reason'])
        audit_service.log(
            request.user, AuditLog.Action.PAYMENT_REFUNDED, donation,
            f'{request.user.full_name} refunded D{donation.amount} donation to "{donation.campaign.title}"',
            metadata={'reason': serializer.validated_data['reason']},
        )
        out = AdminDonationSerializer(donation)
        return donation_service.success_response({'donation': out.data}, message='Donation refunded.')
