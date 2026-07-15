from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_spectacular.utils import extend_schema
from permissions.base import HasResourceAccess
from permissions.roles import Resource
from .serializers import SiteSettingsSerializer
import services.common_service as common_service


class SiteSettingsView(APIView):
    """Public read so the logo/name/description can render before login;
    only admins can change them."""

    required_resource = Resource.SETTINGS
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == 'PATCH':
            return [HasResourceAccess()]
        return [AllowAny()]

    @extend_schema(summary='Get current site branding settings', responses={200: SiteSettingsSerializer})
    def get(self, request):
        site_settings = common_service.get_site_settings()
        return common_service.success_response(SiteSettingsSerializer(site_settings, context={'request': request}).data)

    @extend_schema(summary='[Admin] Update site branding settings', request=SiteSettingsSerializer)
    def patch(self, request):
        site_settings = common_service.get_site_settings()
        serializer = SiteSettingsSerializer(site_settings, data=request.data, partial=True, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return common_service.success_response(serializer.data, message='Site settings updated.')
