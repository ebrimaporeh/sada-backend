from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, extend_schema_view

from permissions.base import IsAdminUser, IsOwnerOrAdmin
from services import user_service
from .serializers import UserSerializer, UserUpdateSerializer, AdminUserSerializer


@extend_schema(tags=['Users'])
class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return UserUpdateSerializer
        return UserSerializer

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        user_service.update_user(self.request.user, **serializer.validated_data)


@extend_schema(tags=['Users'])
class UserListView(generics.ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return user_service.get_all_users()


@extend_schema(tags=['Users'])
class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminUserSerializer

    def get_object(self):
        return user_service.get_user_by_id(self.kwargs['pk'])

    def perform_update(self, serializer):
        user_service.update_user(self.get_object(), **serializer.validated_data)

    def perform_destroy(self, instance):
        user_service.deactivate_user(instance, requesting_user=self.request.user)
