from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema
from permissions.base import HasResourceAccess
from permissions.roles import (
    Resource, RESOURCE_GROUPS, SHORT_ACTION_LABELS,
    get_managed_roles_with_labels, get_role_resources, set_role_resources,
    create_role, delete_role,
)
from .serializers import RoleResourcesUpdateSerializer, RoleCreateSerializer
import services.audit_service as audit_service
from apps.audit.models import AuditLog


def _role_entry(slug, name):
    return {
        'role': slug,
        'label': name,
        'resources': sorted(get_role_resources(slug)),
    }


def _resources_payload():
    return [
        {
            'entity': group['entity'],
            'label': group['label'],
            'actions': [{'key': key, 'label': SHORT_ACTION_LABELS[key]} for key in group['resources']],
        }
        for group in RESOURCE_GROUPS
    ]


class AdminRolePermissionsListView(APIView):
    """Backs the Staff page's Roles & Permissions tab: every runtime role's
    current resource set (grouped by entity for the checklist UI), plus the
    full catalog of grantable resources."""
    permission_classes = [HasResourceAccess]
    required_resource = Resource.ROLES_MANAGE

    @extend_schema(summary='[Admin] List roles and their current resource permissions')
    def get(self, request):
        return Response({
            'success': True,
            'data': {
                'resources': _resources_payload(),
                'roles': [_role_entry(slug, name) for slug, name in get_managed_roles_with_labels()],
            },
        })

    @extend_schema(summary='[Admin] Create a new staff role', request=RoleCreateSerializer)
    def post(self, request):
        serializer = RoleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            role = create_role(
                name=serializer.validated_data['name'],
                resources=serializer.validated_data.get('resources', []),
            )
        except ValueError as e:
            return Response({'success': False, 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        audit_service.log(
            request.user, AuditLog.Action.USER_ROLE_CHANGED, None,
            f'{request.user.full_name} created role "{role.name}"',
            metadata={'role': role.slug, 'resources': sorted(get_role_resources(role.slug))},
        )
        return Response(
            {'success': True, 'message': f'Role "{role.name}" created.', 'data': _role_entry(role.slug, role.name)},
            status=status.HTTP_201_CREATED,
        )


class AdminRolePermissionsUpdateView(APIView):
    """Admin-editable at runtime — replaces a role's Group permissions
    wholesale with whatever set the request sends, taking effect
    immediately for every user holding that role (no deploy, no restart).
    DELETE removes the role entirely, refused while any staff member still
    holds it."""
    permission_classes = [HasResourceAccess]
    required_resource = Resource.ROLES_MANAGE

    def _get_role_or_400(self, role):
        from apps.rbac.models import Role
        try:
            return Role.objects.get(slug=role)
        except Role.DoesNotExist:
            return None

    @extend_schema(summary="[Admin] Replace a role's resource permissions", request=RoleResourcesUpdateSerializer)
    def patch(self, request, role):
        instance = self._get_role_or_400(role)
        if instance is None:
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
                f'{request.user.full_name} updated {instance.name} role permissions',
                metadata={'role': role, 'resources': sorted(after)},
            )

        return Response({
            'success': True,
            'message': f'{instance.name} permissions updated.',
            'data': _role_entry(role, instance.name),
        })

    @extend_schema(summary='[Admin] Delete a staff role')
    def delete(self, request, role):
        instance = self._get_role_or_400(role)
        if instance is None:
            return Response(
                {'success': False, 'message': f'"{role}" is not a runtime-editable role.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        name = instance.name
        try:
            delete_role(role)
        except ValueError as e:
            return Response({'success': False, 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        audit_service.log(
            request.user, AuditLog.Action.USER_ROLE_CHANGED, None,
            f'{request.user.full_name} deleted role "{name}"',
            metadata={'role': role},
        )
        return Response({'success': True, 'message': f'Role "{name}" deleted.'})
