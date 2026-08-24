"""Single source of truth for role-based access to the admin area.

Backed by Django's own Group/Permission system, plus a real `Role` model
(apps.rbac.models.Role) for the catalog of runtime-creatable staff roles --
an admin can create a brand-new role from the Roles & Permissions screen,
not just edit the two that ship by default (Moderator, Finance Officer).
Each `Role` row maps 1:1 to a Django Group of the same `slug`, kept in sync
with `User.role` by a signal (signals/user_signals.py::sync_role_group_membership).

The actual Permission rows live on `apps.rbac.models.AdminResource` (see
that model's docstring for why). Resources are `<entity>_<action>`
(view/create/edit/delete, plus `campaigns_moderate`/`roles_manage` for the
two that don't fit that shape) -- only entities with a real, distinct
backend operation get a checkbox for it; a read-only screen only ever gets
`_view`.

To add a new resource: add it to `Resource` AND `RESOURCE_GROUPS` below
AND to `AdminResource.Meta.permissions` (apps/rbac/models.py) with the same
codename, then makemigrations rbac. Nothing else needs to change.

To add a new admin-gated endpoint: pick the `Resource` it belongs to, then
set on the view either a single check for every method:

    permission_classes = [HasResourceAccess]
    required_resource = Resource.CAMPAIGNS_VIEW

or, when one view class spans several actions (e.g. GET+PATCH+DELETE on a
detail endpoint), a per-method map instead:

    resource_by_method = {
        'GET': Resource.CATEGORIES_VIEW,
        'PATCH': Resource.CATEGORIES_EDIT,
        'DELETE': Resource.CATEGORIES_DELETE,
    }

See permissions/base.py::HasResourceAccess for how these are read.
"""
from apps.users.models import User

PERMISSIONS_APP_LABEL = 'rbac'


class Resource:
    USERS_VIEW = 'users_view'
    USERS_EDIT = 'users_edit'
    USERS_DELETE = 'users_delete'
    STAFF_VIEW = 'staff_view'
    STAFF_CREATE = 'staff_create'
    STAFF_EDIT = 'staff_edit'
    STAFF_DELETE = 'staff_delete'
    ROLES_MANAGE = 'roles_manage'
    DASHBOARD_VIEW = 'dashboard_view'
    SETTINGS_EDIT = 'settings_edit'
    CAMPAIGNS_VIEW = 'campaigns_view'
    CAMPAIGNS_MODERATE = 'campaigns_moderate'
    CATEGORIES_VIEW = 'categories_view'
    CATEGORIES_CREATE = 'categories_create'
    CATEGORIES_EDIT = 'categories_edit'
    CATEGORIES_DELETE = 'categories_delete'
    REPORTS_VIEW = 'reports_view'
    REPORTS_EDIT = 'reports_edit'
    VERIFICATIONS_VIEW = 'verifications_view'
    VERIFICATIONS_EDIT = 'verifications_edit'
    DONATIONS_VIEW = 'donations_view'
    DONATIONS_EDIT = 'donations_edit'
    FINANCES_VIEW = 'finances_view'
    AUDIT_VIEW = 'audit_view'


# Every action codename that's ever used, mapped to its display word. Kept
# tiny and explicit rather than a generic .capitalize() so "moderate" and
# "manage" (which don't follow the view/create/edit/delete shape) still
# read naturally.
ACTION_LABELS = {
    'view': 'View',
    'create': 'Create',
    'edit': 'Edit',
    'delete': 'Delete',
    'moderate': 'Moderate',
    'manage': 'Manage',
}


def _action_label(resource_key: str) -> str:
    return ACTION_LABELS[resource_key.rsplit('_', 1)[-1]]


# The grouping the admin Roles & Permissions screen actually renders --
# one card per entity, one toggle per action that entity really supports.
# Single source of truth: RESOURCE_LABELS and ALL_RESOURCES below are both
# derived from this instead of maintained separately, so a resource can
# only ever exist in one place.
RESOURCE_GROUPS = [
    {'entity': 'users', 'label': 'Users', 'resources': [Resource.USERS_VIEW, Resource.USERS_EDIT, Resource.USERS_DELETE]},
    {'entity': 'staff', 'label': 'Staff', 'resources': [Resource.STAFF_VIEW, Resource.STAFF_CREATE, Resource.STAFF_EDIT, Resource.STAFF_DELETE]},
    {'entity': 'roles', 'label': 'Roles & Permissions', 'resources': [Resource.ROLES_MANAGE]},
    {'entity': 'campaigns', 'label': 'Campaigns', 'resources': [Resource.CAMPAIGNS_VIEW, Resource.CAMPAIGNS_MODERATE]},
    {'entity': 'categories', 'label': 'Categories', 'resources': [Resource.CATEGORIES_VIEW, Resource.CATEGORIES_CREATE, Resource.CATEGORIES_EDIT, Resource.CATEGORIES_DELETE]},
    {'entity': 'reports', 'label': 'Reports', 'resources': [Resource.REPORTS_VIEW, Resource.REPORTS_EDIT]},
    {'entity': 'verifications', 'label': 'Verifications', 'resources': [Resource.VERIFICATIONS_VIEW, Resource.VERIFICATIONS_EDIT]},
    {'entity': 'donations', 'label': 'Donations', 'resources': [Resource.DONATIONS_VIEW, Resource.DONATIONS_EDIT]},
    {'entity': 'finances', 'label': 'Finances', 'resources': [Resource.FINANCES_VIEW]},
    {'entity': 'dashboard', 'label': 'Dashboard', 'resources': [Resource.DASHBOARD_VIEW]},
    {'entity': 'audit', 'label': 'Audit', 'resources': [Resource.AUDIT_VIEW]},
    {'entity': 'settings', 'label': 'Settings', 'resources': [Resource.SETTINGS_EDIT]},
]

RESOURCE_LABELS = {
    key: f"{group['label']} ({_action_label(key)})"
    for group in RESOURCE_GROUPS for key in group['resources']
}

# Just the action word ("View", "Edit", ...) with no entity name prefixed --
# for the grouped checklist UI, where the entity is already the section
# header, so RESOURCE_LABELS' "Users (View)" would repeat "Users" for no
# reason.
SHORT_ACTION_LABELS = {
    key: _action_label(key)
    for group in RESOURCE_GROUPS for key in group['resources']
}

ALL_RESOURCES = set(RESOURCE_LABELS)

# The first resource in each managed role's set that has a dedicated admin
# page, in priority order — used by the frontend to decide where to land a
# non-admin admin role after login instead of the (admin-only) dashboard,
# and as the redirect target when a route's resource check fails. Computed
# against the role's *current* resources (not a hardcoded per-role route)
# since those can change at runtime — see landingRouteForResources on the
# frontend, which walks this same list.
LANDING_RESOURCE_PRIORITY = (
    Resource.DASHBOARD_VIEW,
    Resource.CAMPAIGNS_VIEW,
    Resource.DONATIONS_VIEW,
    Resource.USERS_VIEW,
    Resource.REPORTS_VIEW,
    Resource.VERIFICATIONS_VIEW,
    Resource.FINANCES_VIEW,
    Resource.AUDIT_VIEW,
    Resource.CATEGORIES_VIEW,
    Resource.SETTINGS_EDIT,
    Resource.STAFF_VIEW,
)


def _group_for_role(slug):
    from django.contrib.auth.models import Group
    group, _ = Group.objects.get_or_create(name=slug)
    return group


def get_managed_role_slugs() -> set:
    """Every runtime-editable role's slug, read straight from the `Role`
    table — the live, admin-editable catalog, not a hardcoded tuple. Not
    cached at import time since the whole point is that new rows can
    appear at any moment without a deploy."""
    from apps.rbac.models import Role
    return set(Role.objects.values_list('slug', flat=True))


def get_managed_roles_with_labels() -> list:
    """`[(slug, name), ...]` for every runtime-editable role, ordered same
    as the model's default ordering (by name)."""
    from apps.rbac.models import Role
    return list(Role.objects.values_list('slug', 'name'))


def get_role_resources(slug) -> set:
    """Current resource set for a managed role, read straight from its
    Group's permissions — the live, admin-editable truth, not a hardcoded
    map. Returns an empty set for anything that isn't a managed role."""
    if slug not in get_managed_role_slugs():
        return set()
    group = _group_for_role(slug)
    return set(
        group.permissions
        .filter(content_type__app_label=PERMISSIONS_APP_LABEL)
        .values_list('codename', flat=True)
    )


def set_role_resources(slug, resources) -> set:
    """Admin-editable: replace a managed role's Group permissions wholesale
    with `resources` (an iterable of Resource keys). Silently drops any
    key that isn't a real resource rather than erroring — a stale/typo'd
    key in the request shouldn't block updating the valid ones."""
    from django.contrib.auth.models import Permission
    if slug not in get_managed_role_slugs():
        raise ValueError(f'"{slug}" is not a runtime-editable role.')
    valid = set(resources) & ALL_RESOURCES
    group = _group_for_role(slug)
    perms = Permission.objects.filter(content_type__app_label=PERMISSIONS_APP_LABEL, codename__in=valid)
    group.permissions.set(perms)
    return valid


def create_role(name: str, resources=None):
    """Create a brand-new staff role — a `Role` row plus its backing Group,
    optionally pre-granted `resources`. `slug` is derived from `name` and
    de-duplicated (name collisions append -2, -3, ...) rather than erroring,
    since the display name is what the admin actually cares about."""
    from django.utils.text import slugify
    from apps.rbac.models import Role

    name = name.strip()
    if not name:
        raise ValueError('Role name is required.')

    base_slug = slugify(name)[:30] or 'role'
    slug = base_slug
    attempt = 1
    while Role.objects.filter(slug=slug).exists():
        attempt += 1
        suffix = f'-{attempt}'
        slug = f'{base_slug[:30 - len(suffix)]}{suffix}'

    role = Role.objects.create(slug=slug, name=name)
    if resources:
        set_role_resources(slug, resources)
    return role


def delete_role(slug: str) -> None:
    """Refuses to delete a role that any user still holds — demoting staff
    out from under them as a side effect of a permissions edit would be a
    surprising, silent way to lose admin access. Reassign them first."""
    from apps.rbac.models import Role
    if User.objects.filter(role=slug).exists():
        raise ValueError('Cannot delete a role while staff members still hold it. Reassign them to a different role first.')
    deleted, _ = Role.objects.filter(slug=slug).delete()
    if deleted:
        _group_for_role(slug).delete()


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
