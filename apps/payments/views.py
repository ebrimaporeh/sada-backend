from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from .serializers import PayoutCreateSerializer, PayoutSerializer
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


class ModemPayWebhookView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary='ModemPay payment webhook', exclude=True)
    def post(self, request):
        result = payment_service.handle_modempay_webhook(request.data, request.headers)
        if result:
            return payment_service.success_response({}, message='Webhook processed.')
        return Response({'error': 'Invalid webhook'}, status=status.HTTP_400_BAD_REQUEST)
