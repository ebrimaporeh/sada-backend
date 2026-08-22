from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema
import services.events_service as events_service
import services.consent_service as consent_service
from .serializers import TrackEventSerializer


class TrackEventView(APIView):
    """Public ingestion point for product-engagement events (campaign
    views/shares/clicks, donation funnel steps) -- see apps/events/models.py
    for the full Type list. Anonymous by design: most of what's tracked
    here happens before/without a donor ever creating an account."""
    permission_classes = [AllowAny]

    @extend_schema(summary='Record a product-engagement event', request=TrackEventSerializer)
    def post(self, request):
        serializer = TrackEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        campaign = None
        slug = data.get('campaign_slug')
        if slug:
            from apps.campaigns.models import Campaign
            campaign = Campaign.objects.filter(slug=slug).first()

        events_service.track(
            data['type'],
            user=request.user if request.user.is_authenticated else None,
            campaign=campaign,
            metadata=data.get('metadata'),
            session_id=data.get('session_id', ''),
            # GenericIPAddressField maps to a real `inet` column on Postgres
            # -- an empty string (get_client_ip()'s no-REMOTE_ADDR fallback)
            # is invalid input there, not just "blank".
            ip_address=consent_service.get_client_ip(request) or None,
        )
        return Response({'success': True}, status=201)
