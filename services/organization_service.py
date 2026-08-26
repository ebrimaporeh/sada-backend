"""Organization CRUD, membership, roles, invitations, and ownership transfer.

Permission checks throughout resolve via OrganizationMembership.role.permissions
(a JSONField list of apps.organizations.permissions.OrganizationPermission
values) -- this is a separate, per-organization system from the platform
RBAC in permissions/roles.py (Django Group/Permission-backed, global). See
apps/organizations/models.py's docstrings for why the mechanism differs
even though the shape (DB-backed roles holding resource grants) is the same.
"""
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.users.models import User, Organization
from apps.organizations.models import OrganizationType, OrganizationRole, OrganizationMembership, OrganizationInvitation
from apps.organizations.permissions import OrganizationPermission, ALL_ORGANIZATION_PERMISSIONS

OWNER_ROLE_NAME = 'Owner'
DEFAULT_MEMBER_ROLE_NAME = 'Member'
# A plain member can create campaigns for the org out of the box; every
# other action needs an explicit grant from someone with manage_members.
DEFAULT_MEMBER_PERMISSIONS = [OrganizationPermission.CREATE_CAMPAIGN]

INVITATION_SALT = 'organization-invitation'
INVITATION_MAX_AGE = 60 * 60 * 24 * 14  # 14 days


def get_membership(user: User, organization: Organization) -> OrganizationMembership | None:
    return OrganizationMembership.objects.filter(user=user, organization=organization).select_related('role').first()


def check_campaign_access(user: User, campaign, required_permission: str = None) -> None:
    """Shared by campaign_service.get_owner_campaign and payment_service's
    payout-request/history lookups, so the "individual vs org-owned
    campaign" access rule is defined exactly once. Individual campaign
    (campaign.organization_id is None): only campaign.owner qualifies,
    required_permission is irrelevant, identical to the pre-org-model
    behavior. Org-owned: the acting user must currently be a member, and
    if required_permission is given (one of
    apps.organizations.permissions.OrganizationPermission), their role
    must grant it. Raises Http404 for "no access at all" (so a non-member
    can't even confirm the campaign exists) and PermissionDenied for
    "member but lacking the specific permission" -- callers let both
    propagate; the frontend can then tell a member "you don't have
    permission" apart from a confusing not-found. Returns None on success."""
    from django.http import Http404

    if campaign.organization_id is None:
        if campaign.owner_id != user.id:
            raise Http404('Campaign not found.')
        return
    membership = get_membership(user, campaign.organization)
    if membership is None:
        raise Http404('Campaign not found.')
    if required_permission and required_permission not in membership.role.permissions:
        raise PermissionDenied(
            f"You don't have permission to do this for {campaign.organization.organization_name}."
        )


def require_permission(user: User, organization: Organization, permission: str) -> OrganizationMembership:
    """Returns the membership on success; raises PermissionDenied otherwise
    (not ValidationError -- this is an authorization failure, and the
    custom exception handler maps PermissionDenied to 403, matching every
    other permission check in this codebase)."""
    membership = get_membership(user, organization)
    if membership is None:
        raise PermissionDenied('You are not a member of this organization.')
    if permission not in membership.role.permissions:
        raise PermissionDenied(f"You don't have permission to do this for {organization.organization_name}.")
    return membership


# ─── Organizations ──────────────────────────────────────────────────────────

def get_user_organizations(user: User) -> 'QuerySet[Organization]':
    return user.organizations


def get_organization(organization_id: str, user: User) -> Organization:
    """Any current member can view the organization's own detail -- this
    is not permission-gated beyond membership itself."""
    from django.shortcuts import get_object_or_404
    organization = get_object_or_404(Organization, pk=organization_id)
    if get_membership(user, organization) is None:
        raise PermissionDenied('You are not a member of this organization.')
    return organization


def get_all_organizations(search: str = None) -> 'QuerySet[Organization]':
    """Every organization -- the admin Fundraisers page's Organizations
    tab. Deliberately not membership-gated (unlike get_organization): the
    caller here is staff with the users_view resource grant, not a member,
    same relationship AdminUserListView/get_regular_users has to individual
    users."""
    qs = Organization.objects.select_related('organization_type').order_by('-created_at')
    if search:
        qs = qs.filter(organization_name__icontains=search)
    return qs


def get_organization_admin(organization_id: str) -> Organization:
    """Admin detail lookup -- no membership check, see get_all_organizations."""
    from django.shortcuts import get_object_or_404
    return get_object_or_404(Organization, pk=organization_id)


@transaction.atomic
def create_organization(
    creator: User, organization_name: str, organization_type_slug: str,
    phone: str = '', phone_2: str = '',
    recovery_email_1: str = '', recovery_email_2: str = '',
) -> Organization:
    try:
        organization_type = OrganizationType.objects.get(slug=organization_type_slug, is_visible=True)
    except OrganizationType.DoesNotExist:
        raise ValidationError('That organization type is not currently available.')

    organization = Organization.objects.create(
        organization_name=organization_name, organization_type=organization_type,
        created_by=creator,
        phone=phone, phone_2=phone_2, recovery_email_1=recovery_email_1, recovery_email_2=recovery_email_2,
    )
    owner_role = OrganizationRole.objects.create(
        organization=organization, name=OWNER_ROLE_NAME, permissions=list(ALL_ORGANIZATION_PERMISSIONS),
    )
    OrganizationRole.objects.create(
        organization=organization, name=DEFAULT_MEMBER_ROLE_NAME, permissions=list(DEFAULT_MEMBER_PERMISSIONS),
    )
    # The creator is the org's first contact person -- there's always a real
    # person to reach the moment the org exists, not just once someone
    # bothers to fill in a "contact person" field.
    OrganizationMembership.objects.create(user=creator, organization=organization, role=owner_role, is_contact_person=True)
    return organization


def set_contact_person(organization: Organization, actor: User, target_user: User, is_contact_person: bool) -> OrganizationMembership:
    """Flags/unflags a member as one of the org's points of contact --
    replaces the old free-text Organization.contact_person_name. Not
    exclusive: any number of members can hold this flag (a "2nd contact
    person" is just another membership row with it set, not a hardcoded
    second slot), and there's no invariant requiring at least one -- same
    "basic, not over-engineered" posture as the rest of this launch-phase
    permission system."""
    require_permission(actor, organization, OrganizationPermission.MANAGE_MEMBERS)
    membership = get_membership(target_user, organization)
    if membership is None:
        raise ValidationError('That user is not a member of this organization.')
    membership.is_contact_person = is_contact_person
    membership.save(update_fields=['is_contact_person'])
    return membership


def get_contact_persons(organization: Organization) -> 'QuerySet[OrganizationMembership]':
    return organization.memberships.filter(is_contact_person=True).select_related('user')


# ─── Roles ───────────────────────────────────────────────────────────────────

def get_roles(organization: Organization) -> 'QuerySet[OrganizationRole]':
    return organization.roles.all()


def create_role(organization: Organization, actor: User, name: str, permissions: list) -> OrganizationRole:
    require_permission(actor, organization, OrganizationPermission.MANAGE_MEMBERS)
    if name in (OWNER_ROLE_NAME, DEFAULT_MEMBER_ROLE_NAME):
        raise ValidationError(f'"{name}" is a reserved role name.')
    invalid = set(permissions) - set(ALL_ORGANIZATION_PERMISSIONS)
    if invalid:
        raise ValidationError(f'Unknown permission(s): {", ".join(sorted(invalid))}')
    role = OrganizationRole(organization=organization, name=name, permissions=list(permissions))
    role.full_clean()
    role.save()
    return role


def update_role(role: OrganizationRole, actor: User, name: str = None, permissions: list = None) -> OrganizationRole:
    require_permission(actor, role.organization, OrganizationPermission.MANAGE_MEMBERS)
    if role.name == OWNER_ROLE_NAME:
        raise ValidationError('The Owner role cannot be edited.')
    update_fields = []
    if name is not None and name != role.name:
        if name in (OWNER_ROLE_NAME, DEFAULT_MEMBER_ROLE_NAME):
            raise ValidationError(f'"{name}" is a reserved role name.')
        role.name = name
        update_fields.append('name')
    if permissions is not None:
        invalid = set(permissions) - set(ALL_ORGANIZATION_PERMISSIONS)
        if invalid:
            raise ValidationError(f'Unknown permission(s): {", ".join(sorted(invalid))}')
        role.permissions = list(permissions)
        update_fields.append('permissions')
    if update_fields:
        role.save(update_fields=update_fields)
    return role


def delete_role(role: OrganizationRole, actor: User) -> None:
    require_permission(actor, role.organization, OrganizationPermission.MANAGE_MEMBERS)
    if role.name in (OWNER_ROLE_NAME, DEFAULT_MEMBER_ROLE_NAME):
        raise ValidationError(f'"{role.name}" is a default role and cannot be deleted.')
    if role.memberships.exists():
        raise ValidationError('This role is still assigned to at least one member.')
    if role.invitations.filter(status=OrganizationInvitation.Status.PENDING).exists():
        raise ValidationError('This role has a pending invitation using it.')
    role.delete()


# ─── Membership ──────────────────────────────────────────────────────────────

def get_members(organization: Organization) -> 'QuerySet[OrganizationMembership]':
    return organization.memberships.select_related('user', 'role').all()


def _blocks_sole_owner_departure(membership: OrganizationMembership) -> bool:
    """True if removing this membership would leave `organization` with no
    Owner-role member while other members remain -- the one invariant this
    whole role/transfer system exists to protect. Shared by remove_member
    and user_service._anonymize_account (self/admin account deletion)."""
    if membership.role.name != OWNER_ROLE_NAME:
        return False
    return membership.organization.memberships.exclude(pk=membership.pk).exists()


def remove_member(organization: Organization, actor: User, target_user: User) -> None:
    """A member can always remove themselves (leaving an org needs no
    special permission); removing someone *else* needs manage_members."""
    target_membership = get_membership(target_user, organization)
    if target_membership is None:
        raise ValidationError('That user is not a member of this organization.')
    removed_by_someone_else = actor.id != target_user.id
    if removed_by_someone_else:
        require_permission(actor, organization, OrganizationPermission.MANAGE_MEMBERS)
    if _blocks_sole_owner_departure(target_membership):
        raise ValidationError(
            f'Transfer ownership of {organization.organization_name} to another member before removing this member.'
        )
    target_membership.delete()

    # Only when someone else removed them -- a member who just left
    # (removed themselves) doesn't need an email telling them what they
    # just did.
    if removed_by_someone_else:
        from emails.tasks import send_organization_member_removed_email_task
        send_organization_member_removed_email_task.delay(str(target_user.id), str(organization.id))


def change_member_role(organization: Organization, actor: User, target_user: User, new_role: OrganizationRole) -> OrganizationMembership:
    require_permission(actor, organization, OrganizationPermission.MANAGE_MEMBERS)
    if new_role.organization_id != organization.id:
        raise ValidationError('That role does not belong to this organization.')
    target_membership = get_membership(target_user, organization)
    if target_membership is None:
        raise ValidationError('That user is not a member of this organization.')
    if target_membership.role.name == OWNER_ROLE_NAME or new_role.name == OWNER_ROLE_NAME:
        raise ValidationError('Use transfer_ownership to change who holds the Owner role.')
    target_membership.role = new_role
    target_membership.save(update_fields=['role'])
    return target_membership


def transfer_ownership(organization: Organization, current_owner: User, new_owner: User) -> None:
    """Atomic swap: new_owner -> Owner role, current_owner -> the org's
    default Member role. Immediate, no accept step on the receiving end --
    the initiator is already the trusted current Owner, unlike an
    invitation from a stranger."""
    current_membership = get_membership(current_owner, organization)
    if current_membership is None or current_membership.role.name != OWNER_ROLE_NAME:
        raise PermissionDenied('Only the current owner can transfer ownership.')
    new_membership = get_membership(new_owner, organization)
    if new_membership is None:
        raise ValidationError('The new owner must already be a member of this organization.')

    owner_role = current_membership.role
    fallback_role = organization.roles.filter(name=DEFAULT_MEMBER_ROLE_NAME).first()
    if fallback_role is None:
        raise ValidationError(f'{organization.organization_name} has no "{DEFAULT_MEMBER_ROLE_NAME}" role to fall back to.')

    with transaction.atomic():
        current_membership.role = fallback_role
        current_membership.save(update_fields=['role'])
        new_membership.role = owner_role
        new_membership.save(update_fields=['role'])


# ─── Invitations ─────────────────────────────────────────────────────────────

def generate_invitation_token(invitation: OrganizationInvitation) -> str:
    """Not stored -- re-derived on demand (the email link and the
    authenticated "my invitations" list both call this independently, see
    OrganizationInvitationSerializer.get_token). signing.dumps() embeds a
    fresh timestamp each call, so two tokens for the same invitation are
    different strings, but both stay valid until INVITATION_MAX_AGE from
    when *they* were generated -- there's no single canonical token to leak
    by generating more than one."""
    return signing.dumps(str(invitation.id), salt=INVITATION_SALT)


def generate_invitation_url(invitation: OrganizationInvitation) -> str:
    return f'{settings.FRONTEND_URL}/invitations?token={generate_invitation_token(invitation)}'


def invite_member(organization: Organization, actor: User, email: str, role: OrganizationRole) -> OrganizationInvitation:
    require_permission(actor, organization, OrganizationPermission.MANAGE_MEMBERS)
    if role.organization_id != organization.id:
        raise ValidationError('That role does not belong to this organization.')
    if role.name == OWNER_ROLE_NAME:
        raise ValidationError('Ownership is granted by transfer, not invitation.')

    email = email.strip().lower()
    if OrganizationMembership.objects.filter(organization=organization, user__email__iexact=email).exists():
        raise ValidationError('That person is already a member of this organization.')
    if OrganizationInvitation.objects.filter(
        organization=organization, email__iexact=email, status=OrganizationInvitation.Status.PENDING,
    ).exists():
        raise ValidationError('There is already a pending invitation for that email.')

    invitation = OrganizationInvitation.objects.create(
        organization=organization, email=email, invited_by=actor, role=role,
    )
    from emails.tasks import send_organization_invitation_email_task
    send_organization_invitation_email_task.delay(str(invitation.id), generate_invitation_url(invitation))
    return invitation


def get_pending_invitations(organization: Organization) -> 'QuerySet[OrganizationInvitation]':
    return organization.invitations.filter(status=OrganizationInvitation.Status.PENDING).select_related('role', 'invited_by')


def get_my_invitations(user: User) -> 'QuerySet[OrganizationInvitation]':
    return OrganizationInvitation.objects.filter(
        email__iexact=user.email, status=OrganizationInvitation.Status.PENDING,
    ).select_related('organization', 'role', 'invited_by')


def _decode_invitation_token(token: str) -> OrganizationInvitation:
    from django.shortcuts import get_object_or_404
    try:
        invitation_id = signing.loads(token, salt=INVITATION_SALT, max_age=INVITATION_MAX_AGE)
    except signing.SignatureExpired:
        raise ValidationError('This invitation link has expired. Ask the organization to resend it.')
    except signing.BadSignature:
        raise ValidationError('Invalid invitation link.')
    invitation = get_object_or_404(OrganizationInvitation, pk=invitation_id)
    return invitation


def preview_invitation(token: str) -> OrganizationInvitation:
    """Public -- lets the frontend show "Org X invited you as Role Y"
    before the person has logged in/registered, since they may not have an
    account yet."""
    return _decode_invitation_token(token)


def accept_invitation(token: str, user: User) -> OrganizationMembership:
    invitation = _decode_invitation_token(token)
    if invitation.status != OrganizationInvitation.Status.PENDING:
        raise ValidationError('This invitation has already been responded to.')
    if invitation.email.lower() != user.email.lower():
        raise ValidationError('This invitation was sent to a different email address than your account.')

    with transaction.atomic():
        invitation.status = OrganizationInvitation.Status.ACCEPTED
        invitation.responded_at = timezone.now()
        invitation.save(update_fields=['status', 'responded_at'])
        membership, _ = OrganizationMembership.objects.get_or_create(
            user=user, organization=invitation.organization, defaults={'role': invitation.role},
        )
    return membership


def reject_invitation(token: str, user: User) -> OrganizationInvitation:
    invitation = _decode_invitation_token(token)
    if invitation.status != OrganizationInvitation.Status.PENDING:
        raise ValidationError('This invitation has already been responded to.')
    if invitation.email.lower() != user.email.lower():
        raise ValidationError('This invitation was sent to a different email address than your account.')

    invitation.status = OrganizationInvitation.Status.REJECTED
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=['status', 'responded_at'])
    return invitation


def cancel_invitation(invitation: OrganizationInvitation, actor: User) -> None:
    require_permission(actor, invitation.organization, OrganizationPermission.MANAGE_MEMBERS)
    if invitation.status != OrganizationInvitation.Status.PENDING:
        raise ValidationError('This invitation has already been responded to.')
    invitation.delete()


def resend_invitation(invitation: OrganizationInvitation, actor: User) -> OrganizationInvitation:
    require_permission(actor, invitation.organization, OrganizationPermission.MANAGE_MEMBERS)
    if invitation.status != OrganizationInvitation.Status.PENDING:
        raise ValidationError('This invitation has already been responded to.')
    from emails.tasks import send_organization_invitation_email_task
    send_organization_invitation_email_task.delay(str(invitation.id), generate_invitation_url(invitation))
    return invitation
