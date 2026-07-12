from rest_framework.permissions import BasePermission, SAFE_METHODS
from apps.users.models import User
from .roles import user_has_resource


class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_staff or request.user.role == User.Role.ADMIN)
        )


class HasResourceAccess(BasePermission):
    """Admin-area permission driven entirely by `permissions/roles.py`'s
    ROLE_RESOURCES map. The view just declares which resource it is:

        permission_classes = [HasResourceAccess]
        required_resource = Resource.CAMPAIGNS_VIEW

    A view with no `required_resource` set always denies — that's a
    programming error (a forgotten tag), not an access decision, so it fails
    closed rather than silently granting access to everyone.
    """

    def has_permission(self, request, view):
        resource = getattr(view, 'required_resource', None)
        if resource is None:
            return False
        return user_has_resource(request.user, resource)


class IsPremiumUser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.is_premium
        )


class IsOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff or request.user.role == User.Role.ADMIN:
            return True
        owner_field = getattr(view, 'owner_field', 'user')
        return getattr(obj, owner_field, None) == request.user


class IsOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        owner_field = getattr(view, 'owner_field', 'user')
        return getattr(obj, owner_field, None) == request.user


class ReadOnly(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS
