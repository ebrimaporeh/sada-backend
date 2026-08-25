from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter

from permissions.base import HasResourceAccess
from permissions.roles import Resource
from pagination.base import StandardResultsPagination
from services import user_service, verification_service, organization_change_service
import services.audit_service as audit_service
from apps.audit.models import AuditLog
from .models import User, Organization
from .serializers import (
    UserSerializer, UserUpdateSerializer, AdminUserSerializer, AdminUserListSerializer, AdminUserCreateSerializer,
    IdentityVerificationSerializer, IdentityVerificationCreateSerializer, PublicCampaignerSerializer,
    OrganizationSerializer, OrganizationVerificationSerializer, OrganizationVerificationCreateSerializer,
    OrganizationChangeRequestSerializer, OrganizationChangeRequestCreateSerializer,
    DeleteAccountSerializer,
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
        user = self.request.user
        user_service.update_user(user, **serializer.validated_data)
        audit_service.log(
            user, AuditLog.Action.USER_PROFILE_UPDATED, user,
            f'{user.full_name} updated their profile',
            metadata={'fields': list(serializer.validated_data.keys())},
        )

    @extend_schema(summary='Delete my account', request=DeleteAccountSerializer)
    def delete(self, request):
        serializer = DeleteAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Captured before delete_own_account() runs -- it anonymizes the
        # user's name/email as part of the deletion itself, so logging
        # after would record the log entry against already-scrubbed fields.
        user, name, email = request.user, request.user.full_name, request.user.email
        user_service.delete_own_account(user, password=serializer.validated_data.get('password', ''))
        audit_service.log(
            user, AuditLog.Action.USER_ACCOUNT_DELETED, None, f'{name} deleted their account ({email})',
            actor_name=name, actor_email=email,
        )
        return Response({'success': True, 'message': 'Account deleted.'}, status=status.HTTP_200_OK)


@extend_schema(tags=['Users'], summary='Upload my avatar', responses={200: UserSerializer})
class MyAvatarUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = user_service.upload_avatar(request.user, request.FILES.get('avatar'))
        serializer = UserSerializer(user, context={'request': request})
        return Response({'success': True, 'message': 'Avatar updated.', 'data': serializer.data})


@extend_schema(tags=['Users'], summary='[Admin] Upload any user\'s avatar', responses={200: AdminUserSerializer})
class AdminUserAvatarUploadView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.USERS_EDIT

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        user = user_service.upload_avatar(target, request.FILES.get('avatar'))
        serializer = AdminUserSerializer(user, context={'request': request})
        return Response({'success': True, 'message': 'Avatar updated.', 'data': serializer.data})


@extend_schema(tags=['Users'], summary="[Admin] Upload any organization's logo", responses={200: AdminUserSerializer})
class AdminOrganizationLogoUploadView(APIView):
    """`pk` is an Organization id, not a User id -- an org can have several
    members now, so "upload a logo for user X's org" is ambiguous; this
    always targets one specific organization directly."""
    permission_classes = [HasResourceAccess]
    required_resource = Resource.USERS_EDIT

    def post(self, request, pk):
        organization = get_object_or_404(Organization, pk=pk)
        user_service.upload_organization_logo(organization, request.FILES.get('logo'))
        serializer = OrganizationSerializer(organization, context={'request': request})
        return Response({'success': True, 'message': 'Organization logo updated.', 'data': serializer.data})


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
    parameters=[OpenApiParameter('search', str, description='Search by name, email, or organization name')],
)
class UserListView(generics.ListAPIView):
    serializer_class = AdminUserListSerializer
    permission_classes = [HasResourceAccess]
    required_resource = Resource.USERS_VIEW
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        filters = {}
        search = self.request.query_params.get('search')
        if search:
            filters['search'] = search
        return user_service.get_regular_users(filters)


@extend_schema(tags=['Users'], summary='[Admin] List staff (admin/moderator/finance officer)')
class AdminStaffListView(generics.ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [HasResourceAccess]
    required_resource = Resource.STAFF_VIEW

    def get_queryset(self):
        return user_service.get_staff_users()


@extend_schema(tags=['Users'], summary='[Admin] Onboard a new staff member', request=AdminUserCreateSerializer)
class AdminUserCreateView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.STAFF_CREATE

    def post(self, request):
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = user_service.admin_create_user(
            requesting_user=request.user,
            **serializer.validated_data,
        )
        audit_service.log(
            request.user, AuditLog.Action.STAFF_CREATED, user,
            f'{request.user.full_name} created staff account for {user.full_name} ({user.role})',
        )
        out = AdminUserSerializer(user, context={'request': request})
        return Response(
            {'success': True, 'message': "Staff account created — they'll receive an email to set their password.", 'data': {'user': out.data}},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=['Users'], summary='[Admin] Change a staff member\'s role')
class AdminStaffRoleChangeView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.STAFF_EDIT

    def post(self, request, pk):
        user = user_service.get_user_by_id(pk)
        role = request.data.get('role')
        old_role = user.role
        updated = user_service.change_staff_role(user, role, requesting_user=request.user)
        audit_service.log(
            request.user, AuditLog.Action.USER_ROLE_CHANGED, updated,
            f"{request.user.full_name} changed {updated.full_name}'s role from {old_role} to {updated.role}",
            metadata={'old_role': old_role, 'new_role': updated.role},
        )
        out = AdminUserSerializer(updated, context={'request': request})
        return Response({'success': True, 'message': 'Role updated.', 'data': {'user': out.data}})


@extend_schema(tags=['Users'], summary='[Admin] User stats')
class UserStatsView(generics.GenericAPIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.USERS_VIEW

    def get(self, request):
        return Response({'success': True, 'data': user_service.get_user_stats()})


def _user_detail_resource(request, obj):
    """One endpoint serves both regular users and staff (same `User` model),
    so which resource applies depends on the *target* row, not just the
    HTTP method — a staff target needs the staff_* resources, a regular
    user needs the users_* ones."""
    is_staff_target = user_service.is_staff_role(obj.role)
    if request.method == 'GET':
        return Resource.STAFF_VIEW if is_staff_target else Resource.USERS_VIEW
    if request.method == 'DELETE':
        return Resource.STAFF_DELETE if is_staff_target else Resource.USERS_DELETE
    return Resource.STAFF_EDIT if is_staff_target else Resource.USERS_EDIT


@extend_schema(tags=['Users'])
class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [HasResourceAccess]
    resource_by_target = staticmethod(_user_detail_resource)
    serializer_class = AdminUserSerializer

    def get_object(self):
        obj = user_service.get_user_by_id(self.kwargs['pk'])
        self.check_object_permissions(self.request, obj)
        return obj

    def perform_update(self, serializer):
        user_service.admin_update_user(serializer.instance, self.request.user, **serializer.validated_data)

    def perform_destroy(self, instance):
        # Captured before admin_delete_user() runs -- it anonymizes the
        # target's name/email as part of the deletion itself, so logging
        # after would record the entry against already-scrubbed fields.
        name, email = instance.full_name, instance.email
        user_service.admin_delete_user(instance, requesting_user=self.request.user)
        audit_service.log(
            self.request.user, AuditLog.Action.USER_ACCOUNT_DELETED, None,
            f"{self.request.user.full_name} deleted {name}'s account ({email})",
        )


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
    required_resource = Resource.VERIFICATIONS_VIEW
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        return verification_service.get_all_verifications(
            status=self.request.query_params.get('status'),
            user_id=self.request.query_params.get('user_id'),
        )


@extend_schema(tags=['Verification'], summary='[Admin] Approve or reject a verification request')
class AdminVerificationActionView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.VERIFICATIONS_EDIT

    def post(self, request, pk, action):
        if action == 'approve':
            verification = verification_service.approve_verification(pk, request.user)
            message = 'Verification approved.'
            audit_action, verb = AuditLog.Action.VERIFICATION_APPROVED, 'approved'
        elif action == 'reject':
            verification = verification_service.reject_verification(pk, request.user, request.data.get('reason', ''))
            message = 'Verification rejected.'
            audit_action, verb = AuditLog.Action.VERIFICATION_REJECTED, 'rejected'
        else:
            return Response({'success': False, 'message': f'Unknown action "{action}".'}, status=status.HTTP_400_BAD_REQUEST)
        audit_service.log(
            request.user, audit_action, verification,
            f"{request.user.full_name} {verb} {verification.user.full_name}'s identity verification",
        )
        out = IdentityVerificationSerializer(verification, context={'request': request})
        return Response({'success': True, 'message': message, 'data': {'verification': out.data}})


@extend_schema(tags=['Verification'], summary='Submit organization verification (contact ID + registration docs)')
class OrganizationVerificationSubmitView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = OrganizationVerificationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization = get_object_or_404(Organization, pk=data.pop('organization_id'))
        verification = verification_service.submit_organization_verification(organization, request.user, **data)
        out = OrganizationVerificationSerializer(verification, context={'request': request})
        return Response(
            {'success': True, 'message': 'Verification request submitted. We’ll review it soon.', 'data': {'verification': out.data}},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=['Verification'], summary="Get an organization's latest verification request",
    parameters=[OpenApiParameter('organization_id', str, required=True)],
)
class MyOrganizationVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        organization = get_object_or_404(Organization, pk=request.query_params.get('organization_id'))
        verification = verification_service.get_latest_organization_verification(organization)
        data = OrganizationVerificationSerializer(verification, context={'request': request}).data if verification else None
        return Response({'success': True, 'data': {'verification': data}})


@extend_schema(tags=['Verification'], summary='[Admin] List all organization verification requests')
class AdminOrganizationVerificationListView(generics.ListAPIView):
    serializer_class = OrganizationVerificationSerializer
    permission_classes = [HasResourceAccess]
    required_resource = Resource.VERIFICATIONS_VIEW
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        return verification_service.get_all_organization_verifications(
            status=self.request.query_params.get('status'),
            organization_id=self.request.query_params.get('organization_id'),
        )


@extend_schema(tags=['Verification'], summary='[Admin] Approve or reject an organization verification request')
class AdminOrganizationVerificationActionView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.VERIFICATIONS_EDIT

    def post(self, request, pk, action):
        if action == 'approve':
            verification = verification_service.approve_organization_verification(pk, request.user)
            message = 'Verification approved.'
            audit_action, verb = AuditLog.Action.VERIFICATION_APPROVED, 'approved'
        elif action == 'reject':
            verification = verification_service.reject_organization_verification(pk, request.user, request.data.get('reason', ''))
            message = 'Verification rejected.'
            audit_action, verb = AuditLog.Action.VERIFICATION_REJECTED, 'rejected'
        else:
            return Response({'success': False, 'message': f'Unknown action "{action}".'}, status=status.HTTP_400_BAD_REQUEST)
        audit_service.log(
            request.user, audit_action, verification,
            f"{request.user.full_name} {verb} {verification.organization.organization_name}'s organization verification",
        )
        out = OrganizationVerificationSerializer(verification, context={'request': request})
        return Response({'success': True, 'message': message, 'data': {'verification': out.data}})


@extend_schema(tags=['Verification'], summary='Request a change to a recovery-critical organization field')
class OrganizationChangeRequestSubmitView(APIView):
    """Phone/phone_2/recovery emails are never editable directly — see
    OrganizationChangeRequest's docstring for why. Phone changes queue for
    admin approval; recovery-email changes instead get confirmed by the
    proposed address itself (see ConfirmRecoveryEmailChangeView) — either
    way nothing is applied until this resolves."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OrganizationChangeRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization = get_object_or_404(Organization, pk=data.pop('organization_id'))
        change_request = organization_change_service.submit_change_request(organization, request.user, **data)
        out = OrganizationChangeRequestSerializer(change_request)
        is_email_field = change_request.field_name in organization_change_service.EMAIL_FIELDS
        message = (
            f'Confirmation link sent to {change_request.proposed_value}. The change applies as soon as it’s clicked.'
            if is_email_field else 'Change request submitted. We’ll review it soon.'
        )
        return Response(
            {'success': True, 'message': message, 'data': {'change_request': out.data}},
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=['Verification'], summary="Confirm a proposed recovery email by the token sent to it")
class ConfirmRecoveryEmailChangeView(APIView):
    """Public — the person clicking this link is proving control of the
    *proposed* recovery email's inbox, not necessarily logged into SADA at
    all (they may not even be a SADA user)."""
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get('token')
        if not token:
            return Response({'success': False, 'message': 'Confirmation token required.'}, status=status.HTTP_400_BAD_REQUEST)
        change_request = organization_change_service.confirm_recovery_email_change(token)
        out = OrganizationChangeRequestSerializer(change_request)
        return Response({'success': True, 'message': f'{change_request.get_field_name_display()} confirmed.', 'data': {'change_request': out.data}})


@extend_schema(tags=['Verification'], summary="Get your organization's change requests")
class MyOrganizationChangeRequestsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        requests = organization_change_service.get_my_change_requests(request.user)
        data = OrganizationChangeRequestSerializer(requests, many=True).data
        return Response({'success': True, 'data': {'change_requests': data}})


@extend_schema(tags=['Verification'], summary='[Admin] List all organization change requests')
class AdminOrganizationChangeRequestListView(generics.ListAPIView):
    serializer_class = OrganizationChangeRequestSerializer
    permission_classes = [HasResourceAccess]
    required_resource = Resource.VERIFICATIONS_VIEW
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        return organization_change_service.get_all_change_requests(
            status=self.request.query_params.get('status'),
            organization_id=self.request.query_params.get('organization_id'),
        )


@extend_schema(tags=['Verification'], summary='[Admin] Approve or reject an organization change request')
class AdminOrganizationChangeRequestActionView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.VERIFICATIONS_EDIT

    def post(self, request, pk, action):
        if action == 'approve':
            change_request = organization_change_service.approve_change_request(pk, request.user)
            message = 'Change request approved.'
        elif action == 'reject':
            change_request = organization_change_service.reject_change_request(pk, request.user, request.data.get('reason', ''))
            message = 'Change request rejected.'
        else:
            return Response({'success': False, 'message': f'Unknown action "{action}".'}, status=status.HTTP_400_BAD_REQUEST)
        out = OrganizationChangeRequestSerializer(change_request)
        return Response({'success': True, 'message': message, 'data': {'change_request': out.data}})
