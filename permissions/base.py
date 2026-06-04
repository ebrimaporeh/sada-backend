from rest_framework.permissions import BasePermission, SAFE_METHODS
from apps.users.models import User


class IsAdminUser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_staff or request.user.role == User.Role.ADMIN)
        )


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
