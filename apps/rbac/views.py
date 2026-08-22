from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema
from permissions.base import HasResourceAccess
from permissions.roles import (
    Resource, RESOURCE_LABELS, ALL_RESOURCES, MANAGED_ROLES,
    get_role_resources, set_role_resources,
)
from apps.users.models import User
from .serializers import RoleResourcesUpdateSerializer
import services.audit_service as audit_service
from apps.audit.models import AuditLog


def _role_entry(role):
    return {
        'role': role,
        'label': User.Role(role).label,
        'resources': sorted(get_role_resources(role)),
    }


class AdminRolePermissionsListView(APIView):
    """Backs the Staff page's role-permissions editor: every runtime-
    editable role's current resource set, plus the full list of resources
    that can be granted."""
    permission_classes = [HasResourceAccess]
    required_resource = Resource.STAFF

    @extend_schema(summary='[Admin] List roles and their current resource permissions')
    def get(self, request):
        return Response({
            'success': True,
            'data': {
                'resources': [
                    {'key': key, 'label': RESOURCE_LABELS[key]} for key in sorted(ALL_RESOURCES)
                ],
                'roles': [_role_entry(role) for role in MANAGED_ROLES],
            },
        })


class AdminRolePermissionsUpdateView(APIView):
    """Admin-editable at runtime — replaces a role's Group permissions
    wholesale with whatever set the request sends, taking effect
    immediately for every user holding that role (no deploy, no restart)."""
    permission_classes = [HasResourceAccess]
    required_resource = Resource.STAFF

    @extend_schema(summary="[Admin] Replace a role's resource permissions", request=RoleResourcesUpdateSerializer)
    def patch(self, request, role):
        if role not in MANAGED_ROLES:
            return Response(
                {'success': False, 'message': f'"{role}" is not a runtime-editable role.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = RoleResourcesUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        before = get_role_resources(role)
        after = set_role_resources(role, serializer.validated_data['resources'])

        if before != after:
            audit_service.log(
                request.user, AuditLog.Action.USER_ROLE_CHANGED, None,
                f'{request.user.full_name} updated {User.Role(role).label} role permissions',
                metadata={'role': role, 'resources': sorted(after)},
            )

        return Response({
            'success': True,
            'message': f'{User.Role(role).label} permissions updated.',
            'data': _role_entry(role),
        })
