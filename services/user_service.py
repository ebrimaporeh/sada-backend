from django.core.exceptions import ValidationError, PermissionDenied
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


def create_user(email: str, password: str, **kwargs) -> User:
    if User.objects.filter(email=email.lower()).exists():
        raise ValidationError('A user with this email already exists.')
    user = User(email=email.lower(), **kwargs)
    user.set_password(password)
    user.save()
    return user


def admin_create_user(email: str, role: str, requesting_user: User, first_name: str = '', last_name: str = '', phone: str = '') -> User:
    """Admin-initiated onboarding for a new staff member (moderator or finance
    officer). Regular users self-register — this is exclusively for staff.

    No password is set by the admin — a random unusable-to-guess one is
    generated and the new account is sent a password-reset link (reusing the
    existing django-rest-passwordreset flow) so they set their own password
    on first login, same as any self-service reset.
    """
    if not (requesting_user.is_staff or requesting_user.role == User.Role.ADMIN):
        raise PermissionDenied('Only admins can create staff accounts.')
    if role not in {User.Role.MODERATOR, User.Role.FINANCE_OFFICER}:
        raise ValidationError('Role must be "moderator" or "finance_officer".')

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
        'first_name', 'last_name', 'phone', 'bio', 'region', 'avatar',
        'default_payment_provider', 'default_payment_phone',
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


STAFF_ROLES = {User.Role.ADMIN, User.Role.MODERATOR, User.Role.FINANCE_OFFICER}

# Roles assignable via the staff role-change endpoint. Deliberately excludes
# ADMIN — promoting someone to full admin is sensitive enough that it stays a
# manual, deliberate action outside this UI, not a dropdown swap. Demoting an
# existing admin down to one of these is allowed (that's a safe direction).
STAFF_ASSIGNABLE_ROLES = {User.Role.USER, User.Role.MODERATOR, User.Role.FINANCE_OFFICER}


def get_regular_users(filters: dict = None) -> 'QuerySet[User]':
    """Everyone who isn't staff — the audience for the admin Users page."""
    qs = User.objects.exclude(role__in=STAFF_ROLES)
    if filters:
        qs = qs.filter(**filters)
    return qs


def get_staff_users(filters: dict = None) -> 'QuerySet[User]':
    """Admins, moderators, and finance officers — the audience for the Staff page."""
    qs = User.objects.filter(role__in=STAFF_ROLES)
    if filters:
        qs = qs.filter(**filters)
    return qs


def change_staff_role(user: User, role: str, requesting_user: User) -> User:
    if not (requesting_user.is_staff or requesting_user.role == User.Role.ADMIN):
        raise PermissionDenied('Only admins can change staff roles.')
    if role not in STAFF_ASSIGNABLE_ROLES:
        raise ValidationError('Role must be "user", "moderator", or "finance_officer".')
    user.role = role
    user.save(update_fields=['role'])
    return user


def deactivate_user(user: User, requesting_user: User) -> None:
    if not requesting_user.is_staff:
        raise PermissionDenied('Only admins can deactivate users.')
    user.is_active = False
    user.save(update_fields=['is_active'])


def activate_user(user: User, requesting_user: User) -> None:
    if not requesting_user.is_staff:
        raise PermissionDenied('Only admins can activate users.')
    user.is_active = True
    user.save(update_fields=['is_active'])
