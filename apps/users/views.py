from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema, extend_schema_view

from permissions.base import HasResourceAccess
from permissions.roles import Resource
from pagination.base import StandardResultsPagination
from services import user_service, verification_service
from .serializers import (
    UserSerializer, UserUpdateSerializer, AdminUserSerializer, AdminUserCreateSerializer,
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


@extend_schema(tags=['Users'], summary='[Admin] List regular (non-staff) users')
class UserListView(generics.ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [HasResourceAccess]
    required_resource = Resource.USERS

    def get_queryset(self):
        return user_service.get_regular_users()


@extend_schema(tags=['Users'], summary='[Admin] List staff (admin/moderator/finance officer)')
class AdminStaffListView(generics.ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [HasResourceAccess]
    required_resource = Resource.STAFF

    def get_queryset(self):
        return user_service.get_staff_users()


@extend_schema(tags=['Users'], summary='[Admin] Onboard a new staff member (moderator or finance officer)', request=AdminUserCreateSerializer)
class AdminUserCreateView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.STAFF

    def post(self, request):
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = user_service.admin_create_user(
            requesting_user=request.user,
            **serializer.validated_data,
        )
        out = AdminUserSerializer(user, context={'request': request})
        return Response(
            {'success': True, 'message': "Staff account created — they'll receive an email to set their password.", 'data': {'user': out.data}},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=['Users'], summary='[Admin] Change a staff member\'s role')
class AdminStaffRoleChangeView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.STAFF

    def post(self, request, pk):
        user = user_service.get_user_by_id(pk)
        role = request.data.get('role')
        updated = user_service.change_staff_role(user, role, requesting_user=request.user)
        out = AdminUserSerializer(updated, context={'request': request})
        return Response({'success': True, 'message': 'Role updated.', 'data': {'user': out.data}})


@extend_schema(tags=['Users'], summary='[Admin] User stats')
class UserStatsView(generics.GenericAPIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.USERS

    def get(self, request):
        return Response({'success': True, 'data': user_service.get_user_stats()})


@extend_schema(tags=['Users'])
class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.USERS
    serializer_class = AdminUserSerializer

    def get_object(self):
        return user_service.get_user_by_id(self.kwargs['pk'])

    def perform_update(self, serializer):
        user_service.admin_update_user(serializer.instance, self.request.user, **serializer.validated_data)

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
    permission_classes = [HasResourceAccess]
    required_resource = Resource.VERIFICATIONS
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        return verification_service.get_all_verifications(
            status=self.request.query_params.get('status'),
            user_id=self.request.query_params.get('user_id'),
        )


@extend_schema(tags=['Verification'], summary='[Admin] Approve or reject a verification request')
class AdminVerificationActionView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.VERIFICATIONS

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
