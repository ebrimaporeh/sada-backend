from django.core.exceptions import ValidationError, PermissionDenied
from apps.users.models import User


def get_user_by_id(user_id: str) -> User:
    try:
        return User.objects.get(id=user_id, is_active=True)
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


def create_user(email: str, password: str, **kwargs) -> User:
    if User.objects.filter(email=email.lower()).exists():
        raise ValidationError('A user with this email already exists.')
    user = User(email=email.lower(), **kwargs)
    user.set_password(password)
    user.save()
    return user


def update_user(user: User, **data) -> User:
    allowed_fields = {'first_name', 'last_name', 'phone', 'avatar'}
    update_fields = []
    for field, value in data.items():
        if field in allowed_fields:
            setattr(user, field, value)
            update_fields.append(field)
    if update_fields:
        user.save(update_fields=update_fields)
    return user


def change_user_role(user: User, role: str, requesting_user: User) -> User:
    if not requesting_user.is_staff:
        raise PermissionDenied('Only admins can change user roles.')
    if role not in [r.value for r in User.Role]:
        raise ValidationError(f'Invalid role: {role}')
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
