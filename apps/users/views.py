from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema, extend_schema_view

from permissions.base import IsAdminUser, IsOwnerOrAdmin
from pagination.base import StandardResultsPagination
from services import user_service, verification_service
from .serializers import (
    UserSerializer, UserUpdateSerializer, AdminUserSerializer,
    IdentityVerificationSerializer, IdentityVerificationCreateSerializer,
)


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


@extend_schema(tags=['Users'], summary='[Admin] User stats')
class UserStatsView(generics.GenericAPIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response({'success': True, 'data': user_service.get_user_stats()})


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


@extend_schema(tags=['Verification'], summary='Submit a government ID for identity verification')
class IdentityVerificationSubmitView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = IdentityVerificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verification = verification_service.submit_verification(request.user, **serializer.validated_data)
        out = IdentityVerificationSerializer(verification, context={'request': request})
        return Response(
            {'success': True, 'message': 'Verification request submitted. We’ll review it soon.', 'data': {'verification': out.data}},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=['Verification'], summary='Get your own latest verification request')
class MyVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        verification = verification_service.get_latest_verification(request.user)
        data = IdentityVerificationSerializer(verification, context={'request': request}).data if verification else None
        return Response({'success': True, 'data': {'verification': data}})


@extend_schema(tags=['Verification'], summary='[Admin] List all identity verification requests')
class AdminVerificationListView(generics.ListAPIView):
    serializer_class = IdentityVerificationSerializer
    permission_classes = [IsAdminUser]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        return verification_service.get_all_verifications(status=self.request.query_params.get('status'))


@extend_schema(tags=['Verification'], summary='[Admin] Approve or reject a verification request')
class AdminVerificationActionView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk, action):
        if action == 'approve':
            verification = verification_service.approve_verification(pk, request.user)
            message = 'Verification approved.'
        elif action == 'reject':
            verification = verification_service.reject_verification(pk, request.user, request.data.get('reason', ''))
            message = 'Verification rejected.'
        else:
            return Response({'success': False, 'message': f'Unknown action "{action}".'}, status=status.HTTP_400_BAD_REQUEST)
        out = IdentityVerificationSerializer(verification, context={'request': request})
        return Response({'success': True, 'message': message, 'data': {'verification': out.data}})
