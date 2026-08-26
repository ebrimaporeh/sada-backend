from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from apps.core.models import BaseModel
from .permissions import ALL_ORGANIZATION_PERMISSIONS


class OrganizationType(BaseModel):
    """DB-backed catalog of organization types — mirrors the runtime-editable
    Role pattern (apps.rbac.models.Role) rather than a hardcoded TextChoices,
    since the final set of types/workflows isn't fixed yet (this is a launch
    pad for a future institutional platform).

    `is_visible` gates what's selectable at org-creation time this launch:
    crowdfunding-eligible types only. Company/Government Agency exist as
    rows (so nothing has to be re-migrated when they're switched on) but
    start with is_visible=False — data exists, UI doesn't offer them.
    """
    slug = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_visible = models.BooleanField(
        default=True,
        help_text='Whether this type is selectable when creating a new organization.',
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Organization Type'
        verbose_name_plural = 'Organization Types'

    def __str__(self):
        return self.name


class OrganizationRole(BaseModel):
    """A per-organization custom position (e.g. "Owner", "Manager") holding
    a set of org-scoped permissions. Deliberately not built on Django's
    Group/Permission system the way platform staff roles are — those are
    global, and a role here only ever applies to members of one specific
    organization, so a plain per-row permission list is the simpler fit.

    `permissions` is a JSONField list of OrganizationPermission values
    rather than a M2M/junction table — kept as the least machinery that's
    still fully data-driven per-org, consistent with this being a "basic"
    system for launch (see apps.organizations.permissions).
    """
    organization = models.ForeignKey('users.Organization', on_delete=models.CASCADE, related_name='roles')
    name = models.CharField(max_length=50)
    permissions = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['name']
        unique_together = [('organization', 'name')]
        verbose_name = 'Organization Role'
        verbose_name_plural = 'Organization Roles'

    def __str__(self):
        return f'{self.name} ({self.organization.organization_name})'

    def clean(self):
        invalid = set(self.permissions) - set(ALL_ORGANIZATION_PERMISSIONS)
        if invalid:
            raise ValidationError({'permissions': f'Unknown permission(s): {", ".join(sorted(invalid))}'})


class OrganizationMembership(BaseModel):
    """A user's membership in one organization, with the role/permission set
    that applies while acting as that organization. No `status` field —
    unlike OrganizationInvitation, a membership row only ever exists once
    accepted/created, so it's simply present or removed (see
    organization_service.remove_member); there's no third state to track.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='organization_memberships')
    organization = models.ForeignKey('users.Organization', on_delete=models.CASCADE, related_name='memberships')
    role = models.ForeignKey(OrganizationRole, on_delete=models.PROTECT, related_name='memberships')
    # A real member flagged as one of the org's points of contact -- replaces
    # the old free-text Organization.contact_person_name. The creator is
    # flagged automatically at creation (see organization_service.
    # create_organization); any other member can be added/removed via
    # organization_service.set_contact_person. Not exclusive -- any number
    # of members can hold this flag at once (a "2nd contact person" is just
    # a second membership row with this set to True, not a hardcoded slot).
    is_contact_person = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        unique_together = [('user', 'organization')]
        verbose_name = 'Organization Membership'
        verbose_name_plural = 'Organization Memberships'

    def __str__(self):
        return f'{self.user.email} — {self.organization.organization_name} ({self.role.name})'


class OrganizationInvitation(BaseModel):
    """A pending invitation for `email` to join `organization` with `role`.
    Deliberately a separate table from OrganizationMembership, not a
    membership "status" — a rejected/expired invite should never leave a
    trace in the membership table at all.

    Expiry follows the same convention as every other token-link flow in
    this codebase (email verification, recovery-email confirm): enforced at
    verification time via django.core.signing's max_age, not a stored
    EXPIRED status — see organization_service for the signing salt/max_age
    and accept/reject logic.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACCEPTED = 'accepted', 'Accepted'
        REJECTED = 'rejected', 'Rejected'

    organization = models.ForeignKey('users.Organization', on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_organization_invitations',
    )
    role = models.ForeignKey(OrganizationRole, on_delete=models.PROTECT, related_name='invitations')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Organization Invitation'
        verbose_name_plural = 'Organization Invitations'

    def __str__(self):
        return f'{self.email} — {self.organization.organization_name} ({self.status})'
