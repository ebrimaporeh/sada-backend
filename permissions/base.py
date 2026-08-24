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
    """Admin-area permission driven by Django Group/Permission membership
    (see permissions/roles.py::user_has_resource). A view declares its
    resource one of three ways, in this order of precedence:

        # 1. One resource for every HTTP method:
        permission_classes = [HasResourceAccess]
        required_resource = Resource.CAMPAIGNS_VIEW

        # 2. A different resource per HTTP method (e.g. a detail endpoint
        #    that's GET+PATCH+DELETE at different permission levels):
        resource_by_method = {
            'GET': Resource.CATEGORIES_VIEW,
            'PATCH': Resource.CATEGORIES_EDIT,
            'DELETE': Resource.CATEGORIES_DELETE,
        }

        # 3. A resource that depends on the object itself, not just the
        #    method (e.g. UserDetailView covers both regular users and
        #    staff through one endpoint, and which resource applies
        #    depends on which kind the target row is) — set a callable
        #    instead, checked once the object has been fetched:
        resource_by_target = lambda request, obj: Resource.STAFF_EDIT if ... else Resource.USERS_EDIT

    A view with none of these set always denies — that's a programming
    error (a forgotten tag), not an access decision, so it fails closed
    rather than silently granting access to everyone.
    """

    def has_permission(self, request, view):
        if getattr(view, 'resource_by_target', None):
            return True  # real decision deferred to has_object_permission
        resource = self._resolve(request, view)
        if resource is None:
            return False
        return user_has_resource(request.user, resource)

    def has_object_permission(self, request, view, obj):
        resolver = getattr(view, 'resource_by_target', None)
        if resolver is None:
            return True  # already decided in has_permission
        resource = resolver(request, obj)
        if resource is None:
            return False
        return user_has_resource(request.user, resource)

    def _resolve(self, request, view):
        resource_map = getattr(view, 'resource_by_method', None)
        if resource_map:
            return resource_map.get(request.method)
        return getattr(view, 'required_resource', None)


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
