from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from pagination.base import StandardResultsPagination
from permissions.base import HasResourceAccess
from permissions.roles import Resource
from .models import AuditLog
from .serializers import AuditLogSerializer
import services.audit_service as audit_service


class AdminAuditLogListView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.AUDIT_VIEW

    @extend_schema(
        summary='[Admin] List audit log entries',
        parameters=[
            OpenApiParameter('action', str, description='One of AuditLog.Action, e.g. campaign.created'),
            OpenApiParameter('actor', str, description='Filter by acting user id'),
            OpenApiParameter('search', str, description='Matches description, actor email, or target'),
        ],
        responses={200: AuditLogSerializer(many=True)},
    )
    def get(self, request):
        logs = audit_service.get_audit_logs(request.query_params)
        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(logs, request)
        serializer = AuditLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AuditActionChoicesView(APIView):
    """Backs the admin Audit page's action filter dropdown -- one source of
    truth (AuditLog.Action) instead of a hand-copied list on the frontend."""
    permission_classes = [HasResourceAccess]
    required_resource = Resource.AUDIT_VIEW

    @extend_schema(summary='[Admin] List possible audit action types')
    def get(self, request):
        choices = [{'value': value, 'label': label} for value, label in AuditLog.Action.choices]
        return Response({'success': True, 'data': {'actions': choices}})


class AuditActorsListView(APIView):
    """Backs the admin Activity page's "User" filter dropdown -- only
    users who've actually done something audited, not every user."""
    permission_classes = [HasResourceAccess]
    required_resource = Resource.AUDIT_VIEW

    @extend_schema(summary="[Admin] List users who appear as an actor in the audit log")
    def get(self, request):
        actors = audit_service.get_audit_actors()
        data = [{'id': str(user.id), 'name': user.full_name} for user in actors]
        return Response({'success': True, 'data': {'actors': data}})
