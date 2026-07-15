from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema
from permissions.base import HasResourceAccess
from permissions.roles import Resource
from apps.campaigns.serializers import CampaignListSerializer
import services.zakat_service as zakat_service
import services.zakat_recommendation as zakat_recommendation
import services.common_service as common_service
from .serializers import ZakatSettingsSerializer, ZakatCalculationInputSerializer


class ZakatSettingsView(APIView):
    """Public read so the calculator can show the current nisab/percentage
    before a donor does anything; only admins can change them."""

    required_resource = Resource.SETTINGS

    def get_permissions(self):
        if self.request.method == 'PATCH':
            return [HasResourceAccess()]
        return [AllowAny()]

    @extend_schema(summary='Get current Zakat calculation settings', responses={200: ZakatSettingsSerializer})
    def get(self, request):
        settings_obj = zakat_service.get_settings()
        return common_service.success_response(ZakatSettingsSerializer(settings_obj).data)

    @extend_schema(summary='[Admin] Update Zakat calculation settings', request=ZakatSettingsSerializer)
    def patch(self, request):
        settings_obj = zakat_service.get_settings()
        serializer = ZakatSettingsSerializer(settings_obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return common_service.success_response(serializer.data, message='Zakat settings updated.')


class ZakatCalculateView(APIView):
    """Anyone — including guests — can calculate Zakat; it's not tied to
    an account or a donation."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary='Calculate Zakat owed from asset/liability inputs',
        request=ZakatCalculationInputSerializer,
    )
    def post(self, request):
        serializer = ZakatCalculationInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = zakat_service.calculate_zakat(serializer.validated_data)
        return common_service.success_response(result)


class ZakatRecommendedCampaignsView(APIView):
    """Public shortlist of campaigns screened for Zakat eligibility —
    see services/zakat_recommendation.py for the ranking algorithm."""
    permission_classes = [AllowAny]

    @extend_schema(summary='Get campaigns recommended for Zakat', responses={200: CampaignListSerializer(many=True)})
    def get(self, request):
        limit = int(request.query_params.get('limit', 10))
        campaigns = zakat_recommendation.get_recommended_campaigns(limit=limit)
        data = CampaignListSerializer(campaigns, many=True, context={'request': request}).data
        return common_service.success_response(data)
