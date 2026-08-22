"""Single source of truth for role-based access to the admin area.

Backed by Django's own Group/Permission system now, not a hardcoded dict —
MANAGED_ROLES' access is admin-editable at runtime (Settings -> Staff),
which a Python dict baked into the deployed code could never be. The actual
Permission rows live on `apps.rbac.models.AdminResource` (see that model's
docstring for why); each managed role maps 1:1 to a Django Group of the
same name, kept in sync with `User.role` by a signal
(signals/user_signals.py::sync_role_group_membership).

To add a new resource: add it to `Resource` below AND to
`AdminResource.Meta.permissions` (apps/rbac/models.py) with the same
codename, then makemigrations rbac. Nothing else needs to change — every
existing and new managed role can be granted it via the Staff page.

To add a new admin-gated endpoint: pick the `Resource` it belongs to (or
add a new one), then set on the view:

    permission_classes = [HasResourceAccess]
    required_resource = Resource.CAMPAIGNS_VIEW

`Resource.CAMPAIGNS_VIEW` vs `Resource.CAMPAIGNS_MODERATE` is a deliberate
split: "can see campaigns" (list/detail/stats) and "can act on campaigns"
(approve/reject/suspend/edit/upload media) are different levels of trust —
Finance Officers get the former for financial context, not the latter.
"""
from apps.users.models import User

PERMISSIONS_APP_LABEL = 'rbac'


class Resource:
    USERS = 'users'
    STAFF = 'staff'
    DASHBOARD = 'dashboard'
    SETTINGS = 'settings'
    CAMPAIGNS_VIEW = 'campaigns_view'
    CAMPAIGNS_MODERATE = 'campaigns_moderate'
    CATEGORIES = 'categories'
    REPORTS = 'reports'
    VERIFICATIONS = 'verifications'
    DONATIONS = 'donations'
    FINANCES = 'finances'
    AUDIT = 'audit'


RESOURCE_LABELS = {
    Resource.USERS: 'Users',
    Resource.STAFF: 'Staff management',
    Resource.DASHBOARD: 'Dashboard',
    Resource.SETTINGS: 'Platform settings',
    Resource.CAMPAIGNS_VIEW: 'Campaigns (view)',
    Resource.CAMPAIGNS_MODERATE: 'Campaigns (moderate)',
    Resource.CATEGORIES: 'Categories',
    Resource.REPORTS: 'Reports',
    Resource.VERIFICATIONS: 'Verifications',
    Resource.DONATIONS: 'Donations',
    Resource.FINANCES: 'Finances',
    Resource.AUDIT: 'Audit log',
}

ALL_RESOURCES = set(RESOURCE_LABELS)

# Roles whose resource access is admin-editable at runtime via a Django
# Group of the same name. ADMIN is deliberately not included — it always
# gets every resource (see user_has_resource), the same "too sensitive to
# be a runtime toggle" reasoning services.user_service.STAFF_ASSIGNABLE_ROLES
# already applies to promoting someone to full admin.
MANAGED_ROLES = (User.Role.MODERATOR, User.Role.FINANCE_OFFICER)

# The first resource in each managed role's set that has a dedicated admin
# page, in priority order — used by the frontend to decide where to land a
# non-admin admin role after login instead of the (admin-only) dashboard,
# and as the redirect target when a route's resource check fails. Computed
# against the role's *current* resources (not a hardcoded per-role route)
# since those can change at runtime — see landingRouteForResources on the
# frontend, which walks this same list.
LANDING_RESOURCE_PRIORITY = (
    Resource.DASHBOARD,
    Resource.CAMPAIGNS_VIEW,
    Resource.DONATIONS,
    Resource.USERS,
    Resource.REPORTS,
    Resource.VERIFICATIONS,
    Resource.FINANCES,
    Resource.AUDIT,
    Resource.CATEGORIES,
    Resource.SETTINGS,
    Resource.STAFF,
)


def _group_for_role(role):
    from django.contrib.auth.models import Group
    group, _ = Group.objects.get_or_create(name=role)
    return group


def get_role_resources(role) -> set:
    """Current resource set for a managed role, read straight from its
    Group's permissions — the live, admin-editable truth, not a hardcoded
    map. Returns an empty set for anything that isn't a managed role."""
    if role not in MANAGED_ROLES:
        return set()
    group = _group_for_role(role)
    return set(
        group.permissions
        .filter(content_type__app_label=PERMISSIONS_APP_LABEL)
        .values_list('codename', flat=True)
    )


def set_role_resources(role, resources) -> set:
    """Admin-editable: replace a managed role's Group permissions wholesale
    with `resources` (an iterable of Resource keys). Silently drops any
    key that isn't a real resource rather than erroring — a stale/typo'd
    key in the request shouldn't block updating the valid ones."""
    from django.contrib.auth.models import Permission
    if role not in MANAGED_ROLES:
        raise ValueError(f'"{role}" is not a runtime-editable role.')
    valid = set(resources) & ALL_RESOURCES
    group = _group_for_role(role)
    perms = Permission.objects.filter(content_type__app_label=PERMISSIONS_APP_LABEL, codename__in=valid)
    group.permissions.set(perms)
    return valid


def get_user_resources(user) -> set:
    """Every resource this user currently has access to — the dynamic
    source of truth mirrored to the frontend via UserSerializer.resources.
    Permissions can change at runtime now, so a hardcoded frontend map
    would go stale the moment an admin edits a role."""
    if not user or not getattr(user, 'is_authenticated', False):
        return set()
    if user.is_staff or user.role == User.Role.ADMIN:
        return set(ALL_RESOURCES)
    prefix = f'{PERMISSIONS_APP_LABEL}.'
    return {
        perm[len(prefix):] for perm in user.get_all_permissions()
        if perm.startswith(prefix)
    }


def user_has_resource(user, resource: str) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff or user.role == User.Role.ADMIN:  # Django staff/admin escape hatch
        return True
    return user.has_perm(f'{PERMISSIONS_APP_LABEL}.{resource}')
