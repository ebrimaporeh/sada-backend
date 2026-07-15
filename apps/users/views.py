from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter

from permissions.base import HasResourceAccess
from permissions.roles import Resource
from pagination.base import StandardResultsPagination
from services import user_service, verification_service
from .serializers import (
    UserSerializer, UserUpdateSerializer, AdminUserSerializer, AdminUserCreateSerializer,
    IdentityVerificationSerializer, IdentityVerificationCreateSerializer, PublicCampaignerSerializer,
    OrganizationVerificationSerializer, OrganizationVerificationCreateSerializer,
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


@extend_schema(
    tags=['Users'],
    summary='List public campaigner profiles',
    parameters=[
        OpenApiParameter('region', str, description='Filter by region'),
        OpenApiParameter('search', str, description='Search by name'),
    ],
    responses={200: PublicCampaignerSerializer(many=True)},
)
class PublicCampaignerListView(generics.ListAPIView):
    """Anyone with at least one public, non-anonymous campaign — the
    browsable directory. No auth required, nothing sensitive returned."""
    serializer_class = PublicCampaignerSerializer
    permission_classes = [AllowAny]
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        filters = {
            'region': self.request.query_params.get('region'),
            'search': self.request.query_params.get('search'),
        }
        return user_service.get_public_campaigners(filters)


@extend_schema(tags=['Users'], summary='Get a public campaigner profile', responses={200: PublicCampaignerSerializer})
class PublicCampaignerDetailView(generics.RetrieveAPIView):
    serializer_class = PublicCampaignerSerializer
    permission_classes = [AllowAny]
    lookup_url_kwarg = 'id'

    def get_object(self):
        return user_service.get_public_campaigner(self.kwargs['id'])


@extend_schema(
    tags=['Users'],
    summary='[Admin] List regular (non-staff) users',
    parameters=[OpenApiParameter('account_type', str, description='Filter by individual or organization')],
)
class UserListView(generics.ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [HasResourceAccess]
    required_resource = Resource.USERS
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        filters = {}
        account_type = self.request.query_params.get('account_type')
        if account_type:
            filters['account_type'] = account_type
        return user_service.get_regular_users(filters)


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


@extend_schema(tags=['Verification'], summary='Submit organization verification (contact ID + registration docs)')
class OrganizationVerificationSubmitView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = OrganizationVerificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verification = verification_service.submit_organization_verification(request.user, **serializer.validated_data)
        out = OrganizationVerificationSerializer(verification, context={'request': request})
        return Response(
            {'success': True, 'message': 'Verification request submitted. We’ll review it soon.', 'data': {'verification': out.data}},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=['Verification'], summary="Get your organization's latest verification request")
class MyOrganizationVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        verification = verification_service.get_latest_organization_verification(request.user)
        data = OrganizationVerificationSerializer(verification, context={'request': request}).data if verification else None
        return Response({'success': True, 'data': {'verification': data}})


@extend_schema(tags=['Verification'], summary='[Admin] List all organization verification requests')
class AdminOrganizationVerificationListView(generics.ListAPIView):
    serializer_class = OrganizationVerificationSerializer
    permission_classes = [HasResourceAccess]
    required_resource = Resource.VERIFICATIONS
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        return verification_service.get_all_organization_verifications(
            status=self.request.query_params.get('status'),
            user_id=self.request.query_params.get('user_id'),
        )


@extend_schema(tags=['Verification'], summary='[Admin] Approve or reject an organization verification request')
class AdminOrganizationVerificationActionView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.VERIFICATIONS

    def post(self, request, pk, action):
        if action == 'approve':
            verification = verification_service.approve_organization_verification(pk, request.user)
            message = 'Verification approved.'
        elif action == 'reject':
            verification = verification_service.reject_organization_verification(pk, request.user, request.data.get('reason', ''))
            message = 'Verification rejected.'
        else:
            return Response({'success': False, 'message': f'Unknown action "{action}".'}, status=status.HTTP_400_BAD_REQUEST)
        out = OrganizationVerificationSerializer(verification, context={'request': request})
        return Response({'success': True, 'message': message, 'data': {'verification': out.data}})
