from rest_framework.response import Response
from rest_framework import status


def success_response(data, message='Success.', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'message': message, 'data': data}, status=status_code)


def error_response(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': message, 'errors': errors or {}}, status=status_code)


def get_site_settings():
    from apps.common.models import SiteSettings
    return SiteSettings.get_solo()


def get_legal_content():
    from apps.common.models import LegalContent
    return LegalContent.get_solo()
