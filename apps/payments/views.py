from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from permissions.base import HasResourceAccess
from permissions.roles import Resource
from .models import PlatformSettings
from .serializers import PayoutCreateSerializer, PayoutSerializer, PlatformSettingsSerializer
import services.payment_service as payment_service


class PayoutRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Request a payout for a campaign', request=PayoutCreateSerializer, responses={201: PayoutSerializer})
    def post(self, request):
        serializer = PayoutCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payout = payment_service.request_payout(request.user, serializer.validated_data)
        out = PayoutSerializer(payout)
        return payment_service.success_response({'payout': out.data}, status_code=status.HTTP_201_CREATED)


class MyCampaignPayoutListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='List payouts for my campaign', responses={200: PayoutSerializer(many=True)})
    def get(self, request, slug):
        payouts = payment_service.get_campaign_payouts(request.user, slug)
        serializer = PayoutSerializer(payouts, many=True)
        return payment_service.success_response({'payouts': serializer.data})


class PlatformSettingsView(APIView):
    """Anyone can read platform settings (anonymous/guest donors need
    card_payments_enabled to know whether to show that option, campaign
    owners need the fee to preview payout amounts) — only admins can change
    them. Nothing in this payload is sensitive."""

    required_resource = Resource.SETTINGS

    def get_permissions(self):
        if self.request.method == 'PATCH':
            return [HasResourceAccess()]
        return [AllowAny()]

    @extend_schema(summary='Get current platform settings', responses={200: PlatformSettingsSerializer})
    def get(self, request):
        settings_obj = PlatformSettings.get_solo()
        return payment_service.success_response(PlatformSettingsSerializer(settings_obj).data)

    @extend_schema(summary='[Admin] Update platform settings', request=PlatformSettingsSerializer)
    def patch(self, request):
        settings_obj = PlatformSettings.get_solo()
        serializer = PlatformSettingsSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return payment_service.success_response(serializer.data, message='Platform settings updated.')


class ModemPayWebhookView(APIView):
    permission_classes = [AllowAny]
    # Server-to-server traffic authenticated by signature, not by IP-based
    # anon throttling meant for public users — a busy day of donations
    # shouldn't risk ModemPay's callbacks getting 429'd.
    throttle_classes = []

    @extend_schema(summary='ModemPay payment webhook', exclude=True)
    def post(self, request):
        signature = request.headers.get('x-modem-signature', '')
        result = payment_service.handle_modempay_webhook(request.data, signature)
        if result:
            return payment_service.success_response({}, message='Webhook processed.')
        return Response({'error': 'Invalid webhook'}, status=status.HTTP_400_BAD_REQUEST)
