from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework.response import Response

from permissions.base import HasResourceAccess
from permissions.roles import Resource
from pagination.base import StandardResultsPagination
from apps.users.models import User, Organization
from .models import OrganizationType, OrganizationRole, OrganizationMembership, OrganizationInvitation
from .serializers import (
    OrganizationTypeSerializer, OrganizationSerializer, OrganizationCreateSerializer,
    OrganizationRoleSerializer, OrganizationRoleCreateSerializer, OrganizationRoleUpdateSerializer,
    OrganizationMembershipSerializer, UpdateMemberSerializer,
    OrganizationInvitationSerializer, InvitationCreateSerializer,
    AdminOrganizationListSerializer,
)
import services.organization_service as organization_service
import services.audit_service as audit_service
from apps.audit.models import AuditLog


@extend_schema(tags=['Organizations'], summary='List organization types selectable for a new org')
class OrganizationTypeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        types = OrganizationType.objects.filter(is_visible=True)
        return Response({'success': True, 'data': {'types': OrganizationTypeSerializer(types, many=True).data}})


@extend_schema(tags=['Organizations'])
class OrganizationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Create a new organization', request=OrganizationCreateSerializer, responses={201: OrganizationSerializer})
    def post(self, request):
        serializer = OrganizationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = organization_service.create_organization(request.user, **serializer.validated_data)
        audit_service.log(
            request.user, AuditLog.Action.ORGANIZATION_CREATED, organization,
            f'{request.user.full_name} created organization "{organization.organization_name}"',
        )
        out = OrganizationSerializer(organization, context={'request': request})
        return Response({'success': True, 'message': 'Organization created.', 'data': {'organization': out.data}}, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Organizations'], summary='List organizations I belong to')
class MyOrganizationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        organizations = organization_service.get_user_organizations(request.user)
        out = OrganizationSerializer(organizations, many=True, context={'request': request})
        return Response({'success': True, 'data': {'organizations': out.data}})


@extend_schema(tags=['Organizations'])
class OrganizationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    # No PATCH here -- organization_name/organization_type stay fixed post-
    # creation, phone/phone_2/recovery emails go through
    # OrganizationChangeRequest, and "contact person" is now a per-member
    # flag (see OrganizationMemberDetailView.patch), not an org-level field.
    @extend_schema(summary='Get an organization I belong to', responses={200: OrganizationSerializer})
    def get(self, request, pk):
        organization = organization_service.get_organization(pk, request.user)
        out = OrganizationSerializer(organization, context={'request': request})
        return Response({'success': True, 'data': {'organization': out.data}})


@extend_schema(tags=['Organizations'], summary='Transfer ownership to another member')
class TransferOwnershipView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        organization = get_object_or_404(Organization, pk=pk)
        new_owner = get_object_or_404(User, pk=request.data.get('user_id'))
        organization_service.transfer_ownership(organization, request.user, new_owner)
        audit_service.log(
            request.user, AuditLog.Action.ORGANIZATION_OWNERSHIP_TRANSFERRED, organization,
            f'{request.user.full_name} transferred ownership of "{organization.organization_name}" to {new_owner.full_name}',
        )
        return Response({'success': True, 'message': f'Ownership transferred to {new_owner.full_name}.'})


@extend_schema(tags=['Organizations'])
class OrganizationRoleListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='List an organization\'s roles', responses={200: OrganizationRoleSerializer(many=True)})
    def get(self, request, pk):
        organization = organization_service.get_organization(pk, request.user)
        roles = organization_service.get_roles(organization)
        return Response({'success': True, 'data': {'roles': OrganizationRoleSerializer(roles, many=True).data}})

    @extend_schema(summary='Create a custom role', request=OrganizationRoleCreateSerializer, responses={201: OrganizationRoleSerializer})
    def post(self, request, pk):
        organization = get_object_or_404(Organization, pk=pk)
        serializer = OrganizationRoleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = organization_service.create_role(organization, request.user, **serializer.validated_data)
        out = OrganizationRoleSerializer(role)
        return Response({'success': True, 'message': 'Role created.', 'data': {'role': out.data}}, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Organizations'])
class OrganizationRoleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Update a custom role', request=OrganizationRoleUpdateSerializer)
    def patch(self, request, pk, role_id):
        role = get_object_or_404(OrganizationRole, pk=role_id, organization_id=pk)
        serializer = OrganizationRoleUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        role = organization_service.update_role(role, request.user, **serializer.validated_data)
        return Response({'success': True, 'message': 'Role updated.', 'data': {'role': OrganizationRoleSerializer(role).data}})

    @extend_schema(summary='Delete a custom role')
    def delete(self, request, pk, role_id):
        role = get_object_or_404(OrganizationRole, pk=role_id, organization_id=pk)
        organization_service.delete_role(role, request.user)
        return Response({'success': True, 'message': 'Role deleted.'})


@extend_schema(tags=['Organizations'], summary="List an organization's members")
class OrganizationMemberListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        organization = organization_service.get_organization(pk, request.user)
        members = organization_service.get_members(organization)
        return Response({'success': True, 'data': {'members': OrganizationMembershipSerializer(members, many=True).data}})


@extend_schema(tags=['Organizations'])
class OrganizationMemberDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="Change a member's role and/or contact-person flag", request=UpdateMemberSerializer)
    def patch(self, request, pk, user_id):
        organization = get_object_or_404(Organization, pk=pk)
        target_user = get_object_or_404(User, pk=user_id)
        serializer = UpdateMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        membership = None
        if 'role_id' in data:
            role = get_object_or_404(OrganizationRole, pk=data['role_id'], organization=organization)
            membership = organization_service.change_member_role(organization, request.user, target_user, role)
            audit_service.log(
                request.user, AuditLog.Action.ORGANIZATION_MEMBER_ROLE_CHANGED, organization,
                f'{request.user.full_name} changed {target_user.full_name}\'s role in "{organization.organization_name}" to {role.name}',
            )
        if 'is_contact_person' in data:
            membership = organization_service.set_contact_person(organization, request.user, target_user, data['is_contact_person'])

        return Response({'success': True, 'message': 'Member updated.', 'data': {'member': OrganizationMembershipSerializer(membership).data}})

    @extend_schema(summary='Remove a member (or leave, if removing yourself)')
    def delete(self, request, pk, user_id):
        organization = get_object_or_404(Organization, pk=pk)
        target_user = get_object_or_404(User, pk=user_id)
        organization_service.remove_member(organization, request.user, target_user)
        audit_service.log(
            request.user, AuditLog.Action.ORGANIZATION_MEMBER_REMOVED, organization,
            f'{request.user.full_name} removed {target_user.full_name} from "{organization.organization_name}"',
        )
        return Response({'success': True, 'message': 'Member removed.'})


@extend_schema(tags=['Organizations'])
class OrganizationInvitationListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="List an organization's pending invitations", responses={200: OrganizationInvitationSerializer(many=True)})
    def get(self, request, pk):
        organization = organization_service.get_organization(pk, request.user)
        invitations = organization_service.get_pending_invitations(organization)
        return Response({'success': True, 'data': {'invitations': OrganizationInvitationSerializer(invitations, many=True).data}})

    @extend_schema(summary='Invite someone to join', request=InvitationCreateSerializer, responses={201: OrganizationInvitationSerializer})
    def post(self, request, pk):
        organization = get_object_or_404(Organization, pk=pk)
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = get_object_or_404(OrganizationRole, pk=serializer.validated_data['role_id'], organization=organization)
        invitation = organization_service.invite_member(organization, request.user, serializer.validated_data['email'], role)
        out = OrganizationInvitationSerializer(invitation)
        return Response({'success': True, 'message': f'Invitation sent to {invitation.email}.', 'data': {'invitation': out.data}}, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Organizations'])
class OrganizationInvitationActionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Cancel or resend a pending invitation')
    def post(self, request, pk, invitation_id, action):
        invitation = get_object_or_404(OrganizationInvitation, pk=invitation_id, organization_id=pk)
        if action == 'cancel':
            organization_service.cancel_invitation(invitation, request.user)
            return Response({'success': True, 'message': 'Invitation cancelled.'})
        elif action == 'resend':
            organization_service.resend_invitation(invitation, request.user)
            return Response({'success': True, 'message': f'Invitation resent to {invitation.email}.'})
        return Response({'success': False, 'message': f'Unknown action "{action}".'}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['Organizations'], summary='List invitations sent to my email')
class MyInvitationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        invitations = organization_service.get_my_invitations(request.user)
        return Response({'success': True, 'data': {'invitations': OrganizationInvitationSerializer(invitations, many=True).data}})


@extend_schema(
    tags=['Organizations'], summary='Preview an invitation by its token (no login required)',
    parameters=[OpenApiParameter('token', str, required=True)],
)
class InvitationPreviewView(APIView):
    """Public -- the invited person may not have an account yet, so this
    has to work before login/register."""
    permission_classes = [AllowAny]

    def get(self, request):
        token = request.query_params.get('token')
        if not token:
            return Response({'success': False, 'message': 'Token required.'}, status=status.HTTP_400_BAD_REQUEST)
        invitation = organization_service.preview_invitation(token)
        return Response({'success': True, 'data': {'invitation': OrganizationInvitationSerializer(invitation).data}})


@extend_schema(tags=['Organizations'], summary='Accept an invitation')
class InvitationAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get('token')
        if not token:
            return Response({'success': False, 'message': 'Token required.'}, status=status.HTTP_400_BAD_REQUEST)
        membership = organization_service.accept_invitation(token, request.user)
        return Response({
            'success': True, 'message': f'You joined {membership.organization.organization_name}.',
            'data': {'organization': OrganizationSerializer(membership.organization, context={'request': request}).data},
        })


@extend_schema(tags=['Organizations'], summary='Reject an invitation')
class InvitationRejectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get('token')
        if not token:
            return Response({'success': False, 'message': 'Token required.'}, status=status.HTTP_400_BAD_REQUEST)
        organization_service.reject_invitation(token, request.user)
        return Response({'success': True, 'message': 'Invitation declined.'})


# ─── Admin ───────────────────────────────────────────────────────────────────
# Unlike everything above, these aren't membership-gated -- the caller is
# staff with the users_view/users_edit resource grant reviewing ANY
# organization, not a member of the one they're looking at. Same relationship
# AdminUserListView/AdminCampaignListView have to their own regular
# non-admin counterparts.

@extend_schema(
    tags=['Organizations'], summary='[Admin] List all organizations',
    parameters=[OpenApiParameter('search', str, description='Search by organization name')],
)
class AdminOrganizationListView(generics.ListAPIView):
    serializer_class = AdminOrganizationListSerializer
    permission_classes = [HasResourceAccess]
    required_resource = Resource.USERS_VIEW
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        return organization_service.get_all_organizations(search=self.request.query_params.get('search'))


@extend_schema(tags=['Organizations'], summary='[Admin] Get any organization\'s detail')
class AdminOrganizationDetailView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.USERS_VIEW

    def get(self, request, pk):
        organization = organization_service.get_organization_admin(pk)
        return Response({'success': True, 'data': {'organization': OrganizationSerializer(organization, context={'request': request}).data}})


@extend_schema(tags=['Organizations'], summary="[Admin] List any organization's members")
class AdminOrganizationMemberListView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.USERS_VIEW

    def get(self, request, pk):
        organization = organization_service.get_organization_admin(pk)
        members = organization_service.get_members(organization)
        return Response({'success': True, 'data': {'members': OrganizationMembershipSerializer(members, many=True).data}})
