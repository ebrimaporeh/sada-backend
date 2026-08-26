from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.db.models import Count, Sum, Q
from django.shortcuts import get_object_or_404
from apps.users.models import User


def get_user_by_id(user_id: str) -> User:
    try:
        return User.objects.get(id=user_id)
    except User.DoesNotExist:
        raise ValidationError(f'User not found.')


def get_user_by_email(email: str) -> User:
    try:
        return User.objects.get(email=email.lower())
    except User.DoesNotExist:
        raise ValidationError('User not found.')


def get_all_users(filters: dict = None) -> 'QuerySet[User]':
    qs = User.objects.all()
    if filters:
        qs = qs.filter(**filters)
    return qs


def get_user_stats() -> dict:
    return {'total_users': User.objects.count()}


@transaction.atomic
def create_user(email: str, password: str, **kwargs) -> User:
    """Every registration creates an individual account -- an organization
    is no longer something you register *as*, it's something an individual
    creates/joins afterward (see apps.organizations). `account_type` stays
    on User for now (see apps.users.models.User.AccountType docstring) but
    is never set to ORGANIZATION here, and this function no longer accepts
    or does anything with organization-profile fields."""
    if User.objects.filter(email=email.lower()).exists():
        raise ValidationError('A user with this email already exists.')

    user = User(email=email.lower(), **kwargs)
    user.set_password(password)
    user.save()

    return user


def admin_create_user(email: str, role: str, requesting_user: User, first_name: str = '', last_name: str = '', phone: str = '') -> User:
    """Admin-initiated onboarding for a new staff member, in any
    runtime-defined role (see permissions/roles.py::Role). Regular users
    self-register — this is exclusively for staff.

    No password is set by the admin — a random unusable-to-guess one is
    generated and the new account is sent a password-reset link (reusing the
    existing django-rest-passwordreset flow) so they set their own password
    on first login, same as any self-service reset.
    """
    from permissions.roles import get_managed_role_slugs

    if not (requesting_user.is_staff or requesting_user.role == User.Role.ADMIN):
        raise PermissionDenied('Only admins can create staff accounts.')
    if role not in get_managed_role_slugs():
        raise ValidationError('Role must be one of the runtime-editable staff roles.')

    from django.utils.crypto import get_random_string
    random_password = get_random_string(32)

    user = create_user(
        email=email,
        password=random_password,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        role=role,
        email_verified=True,
    )

    from django_rest_passwordreset.signals import reset_password_token_created
    from django_rest_passwordreset.views import generate_token_for_email
    token = generate_token_for_email(email=user.email)
    if token:
        reset_password_token_created.send(sender=None, instance=None, reset_password_token=token)

    return user


def update_user(user: User, **data) -> User:
    allowed_fields = {
        'first_name', 'last_name', 'phone', 'bio', 'region',
        'default_payment_provider', 'default_payment_phone', 'show_total_raised',
        'notify_donations_received', 'notify_campaign_approved',
        'notify_campaign_rejected', 'notify_goal_reached',
        'notify_new_comment', 'notify_new_update', 'notify_marketing',
        'is_active', 'is_verified',
    }
    update_fields = []
    for field, value in data.items():
        if field in allowed_fields:
            setattr(user, field, value)
            update_fields.append(field)
    if update_fields:
        user.save(update_fields=update_fields)
    return user


def _anonymize_account(user: User, *, reset_role: bool = False) -> None:
    """Shared by delete_own_account (self-service) and admin_delete_user
    (staff-initiated): scrubs personally-identifying fields and locks the
    account out, without hard-deleting the User row.

    Doesn't hard-delete: Campaign.owner is CASCADE, so an actual
    `user.delete()` would destroy every campaign this user owns and, via
    Donation.campaign's own CASCADE, every donation ever made to them —
    the Privacy Policy explicitly promises "legally required financial
    records will be retained even after deletion," so that's not
    optional. is_active=False plus an unusable password is enough on its
    own to lock the account out entirely -- SimpleJWT's JWTAuthentication
    checks is_active on every request, so every existing token stops
    working immediately, not just future logins.

    Government-issued ID photos submitted for verification have no such
    retention requirement, so those are deleted outright (file and row),
    not just unlinked from the user.

    `reset_role` additionally demotes the account to a plain User and
    drops it from any staff Group (via the usual role-change signal) --
    only relevant for admin-initiated deletes of a staff member; a
    self-deleting user is never staff in practice, and delete_own_account
    doesn't need this.

    Deleting a user only removes *their own* OrganizationMembership rows --
    an organization an account belongs to is never renamed/scrubbed just
    because one member's account was deleted, since other members may still
    be actively using it. Organization verification submissions
    (organization_verification_requests) are likewise left alone even
    though this user submitted them -- that's the org's own verification
    record now, not the departing individual's, same reasoning as why
    campaigns/donations survive account deletion. Blocked outright if this
    user is the sole Owner-role holder of an organization that still has
    other members (see OrganizationMembership's docstring on the "exactly
    one Owner" invariant) -- transfer ownership first. An org left with
    zero members entirely (this user was its only one) is an acceptable
    launch-phase edge case, not something this guards against.
    """
    from services.organization_service import _blocks_sole_owner_departure
    blocking_orgs = [
        m.organization for m in user.organization_memberships.select_related('organization', 'role').all()
        if _blocks_sole_owner_departure(m)
    ]
    if blocking_orgs:
        names = ', '.join(o.organization_name for o in blocking_orgs)
        raise ValidationError(
            f'Transfer ownership of {names} to another member before deleting this account.'
        )

    with transaction.atomic():
        if user.avatar:
            user.avatar.delete(save=False)

        for verification in user.verification_requests.all():
            for field in (verification.id_photo_front, verification.id_photo_back):
                if field:
                    field.delete(save=False)
        user.verification_requests.all().delete()

        # Leaves every organization this user belonged to -- the org itself
        # (and its verification/change-request history) is untouched, see
        # this function's docstring.
        user.organization_memberships.all().delete()

        user.email = f'deleted-{user.id}@deleted.sada.gm'
        user.first_name = 'Deleted'
        user.last_name = 'User'
        user.phone = ''
        user.bio = ''
        user.region = ''
        user.avatar = None
        user.default_payment_provider = ''
        user.default_payment_phone = ''
        user.google_sub = None
        user.is_active = False
        user.is_deleted = True
        if reset_role:
            user.role = User.Role.USER
        user.set_unusable_password()
        user.save()


def delete_own_account(user: User, password: str = '') -> None:
    """Self-service account deletion.

    Raises ValidationError if `password` doesn't match — skipped entirely
    for an account with no usable password (Google-only sign-in), where
    the caller already being authenticated is the only credential that
    exists to check.
    """
    if user.has_usable_password() and not user.check_password(password):
        raise ValidationError('Incorrect password.')

    # Sent to the real address before it gets overwritten below.
    from services import notification_service
    notification_service.notify_user(
        user, 'Your account has been deleted',
        'This confirms your SADA account and personal information have been deleted, '
        'as requested. Campaign and donation records are retained as required for '
        'financial record-keeping, with your personal details removed from them.',
    )

    _anonymize_account(user)


def admin_delete_user(user: User, requesting_user: User) -> None:
    """Admin-initiated deletion of a user, organization, or staff account —
    same anonymize-not-hard-delete guarantee as delete_own_account (see
    _anonymize_account), just without a password check since the admin
    isn't the account owner.

    Refuses to delete an Admin account (that stays a deliberate, separate
    action outside this UI, same reasoning as promoting someone *to*
    Admin) or the requesting user's own account.
    """
    if not (requesting_user.is_staff or requesting_user.role == User.Role.ADMIN):
        raise PermissionDenied('Only admins can delete accounts.')
    if user.id == requesting_user.id:
        raise ValidationError('You cannot delete your own account.')
    if user.role == User.Role.ADMIN:
        raise ValidationError('Admin accounts cannot be deleted here.')

    was_staff = is_staff_role(user.role)

    from services import notification_service
    notification_service.notify_user(
        user, 'Your account has been deleted',
        'This confirms your SADA account and personal information have been deleted '
        'by an administrator. Campaign and donation records are retained as required '
        'for financial record-keeping, with your personal details removed from them.',
    )

    _anonymize_account(user, reset_role=was_staff)


def upload_avatar(user: User, image_file) -> User:
    if not image_file:
        raise ValueError('No image provided.')
    from services.image_compression import process_image
    user.avatar = process_image(image_file, profile='avatar')
    user.save(update_fields=['avatar'])
    return user


def upload_organization_logo(organization, image_file):
    """Admin-only direct logo set — bypasses the normal path (copied from
    OrganizationVerification.organization_photo on approval) for cases like
    fixing/seeding an org's branding without a full re-verification cycle."""
    if not image_file:
        raise ValueError('No image provided.')
    from services.image_compression import process_image
    organization.logo = process_image(image_file, profile='avatar')
    organization.save(update_fields=['logo'])
    return organization


def admin_update_user(user: User, requesting_user: User, **data) -> User:
    if user.id == requesting_user.id and 'is_active' in data and not data['is_active']:
        raise ValidationError('You cannot deactivate your own account.')

    # Revoking a verified user's badge must reject their underlying approved ID
    # submission too — otherwise is_verified and the verification record's own
    # status silently disagree (this was a recurring real bug), and the user is
    # left with no way to see why or to resubmit.
    if 'is_verified' in data and not data['is_verified'] and user.is_verified:
        from services import verification_service
        verification_service.revoke_verification(user, requesting_user)

    return update_user(user, **data)


def staff_roles() -> set:
    """Admin plus every runtime-defined role (apps.rbac.models.Role) —
    dynamic now that roles aren't a hardcoded pair, so a newly created
    custom role's members are correctly treated as staff everywhere this
    is used (which page they show up on, group-sync, etc.) with no extra
    code needed when the role is created."""
    from permissions.roles import get_managed_role_slugs
    return {User.Role.ADMIN} | get_managed_role_slugs()


def is_staff_role(role: str) -> bool:
    return role in staff_roles()


def get_regular_users(filters: dict = None) -> 'QuerySet[User]':
    """Everyone who isn't staff — the audience for the admin Users page.
    Excludes deleted accounts permanently (see User.is_deleted) -- they're
    kept in the DB for financial record-keeping, not to clutter this list."""
    qs = User.objects.exclude(role__in=staff_roles()).filter(is_deleted=False)
    if filters:
        filters = dict(filters)
        search = filters.pop('search', None)
        if filters:
            qs = qs.filter(**filters)
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) | Q(last_name__icontains=search)
                | Q(email__icontains=search) | Q(organization_memberships__organization__organization_name__icontains=search)
            ).distinct()
    return qs


def get_staff_users(filters: dict = None) -> 'QuerySet[User]':
    """Admins plus every runtime-defined staff role — the audience for the
    Staff page. Excludes deleted accounts (see get_regular_users) --
    admin_delete_user always resets a staff target's role away from staff_
    roles() on delete, so this exclusion is defense-in-depth, not the
    primary guard."""
    qs = User.objects.filter(role__in=staff_roles(), is_deleted=False)
    if filters:
        qs = qs.filter(**filters)
    return qs


def change_staff_role(user: User, role: str, requesting_user: User) -> User:
    from permissions.roles import get_managed_role_slugs

    if not (requesting_user.is_staff or requesting_user.role == User.Role.ADMIN):
        raise PermissionDenied('Only admins can change staff roles.')
    # Deliberately excludes ADMIN — promoting someone to full admin is
    # sensitive enough that it stays a manual, deliberate action outside
    # this UI, not a dropdown swap. Demoting an existing admin down to a
    # managed role is allowed (that's a safe direction).
    if role != User.Role.USER and role not in get_managed_role_slugs():
        raise ValidationError('Role must be "user" or one of the runtime-editable staff roles.')
    user.role = role
    user.save(update_fields=['role'])
    return user


def _public_campaigner_base_queryset():
    """A "campaigner" is derived, not a formal role — any user with at least
    one campaign that's actually publicly visible and not anonymous. Mirrors
    the statuses campaign_service.get_campaign_by_slug() treats as public,
    minus PENDING (not yet approved, so not a real public track record)."""
    from apps.campaigns.models import Campaign
    public_statuses = [Campaign.Status.ACTIVE, Campaign.Status.APPROVED, Campaign.Status.COMPLETED]
    is_public_campaign = Q(campaigns__status__in=public_statuses, campaigns__is_anonymous=False)
    return User.objects.filter(is_public_campaign).distinct().annotate(
        campaign_count=Count('campaigns', filter=is_public_campaign, distinct=True),
        total_raised=Sum('campaigns__raised', filter=is_public_campaign),
    )


def get_public_campaigners(filters=None):
    from apps.campaigns.models import Campaign
    from services import campaigner_ranking

    qs = _public_campaigner_base_queryset()
    if filters:
        if filters.get('region'):
            qs = qs.filter(region=filters['region'])
        if filters.get('search'):
            q = filters['search']
            qs = qs.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q))

    public_statuses = [Campaign.Status.ACTIVE, Campaign.Status.APPROVED, Campaign.Status.COMPLETED]
    qs = campaigner_ranking.annotate_activity(qs, public_statuses)
    return campaigner_ranking.order_by_activity(qs)


def get_public_campaigner(user_id):
    return get_object_or_404(_public_campaigner_base_queryset(), pk=user_id)
