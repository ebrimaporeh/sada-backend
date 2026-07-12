"""Single source of truth for role-based access to the admin area.

To add a new role: add it to `User.Role` (apps/users/models.py) and give it
a resource set in `ROLE_RESOURCES` below — that's it, nothing else in the
codebase needs to change.

To add a new admin-gated endpoint: pick the `Resource` it belongs to (or add
a new one if it's a genuinely new area), then set on the view:

    permission_classes = [HasResourceAccess]
    required_resource = Resource.CAMPAIGNS_VIEW

`Resource.CAMPAIGNS_VIEW` vs `Resource.CAMPAIGNS_MODERATE` is a deliberate
split: "can see campaigns" (list/detail/stats) and "can act on campaigns"
(approve/reject/suspend/edit/upload media) are different levels of trust —
Finance Officers get the former for financial context, not the latter.
"""
from apps.users.models import User


class Resource:
    USERS = 'users'
    STAFF = 'staff'
    DASHBOARD = 'dashboard'
    SETTINGS = 'settings'
    CAMPAIGNS_VIEW = 'campaigns.view'
    CAMPAIGNS_MODERATE = 'campaigns.moderate'
    CATEGORIES = 'categories'
    REPORTS = 'reports'
    VERIFICATIONS = 'verifications'
    DONATIONS = 'donations'
    FINANCES = 'finances'


ALL_RESOURCES = {
    Resource.USERS, Resource.STAFF, Resource.DASHBOARD, Resource.SETTINGS,
    Resource.CAMPAIGNS_VIEW, Resource.CAMPAIGNS_MODERATE, Resource.CATEGORIES,
    Resource.REPORTS, Resource.VERIFICATIONS, Resource.DONATIONS, Resource.FINANCES,
}

# The actual product decision lives here — everything above/below it is
# just plumbing. Read this dict to answer "who can see X?".
ROLE_RESOURCES = {
    User.Role.ADMIN: ALL_RESOURCES,
    User.Role.MODERATOR: {
        Resource.CAMPAIGNS_VIEW, Resource.CAMPAIGNS_MODERATE,
        Resource.CATEGORIES, Resource.REPORTS, Resource.VERIFICATIONS,
    },
    User.Role.FINANCE_OFFICER: {
        Resource.CAMPAIGNS_VIEW, Resource.DONATIONS, Resource.FINANCES,
    },
}

# The first resource in each role's set that has a dedicated admin page —
# used by the frontend to decide where to land a non-admin admin role after
# login instead of the (admin-only) dashboard. Kept here, next to the access
# map it depends on, rather than guessed at in the frontend.
ROLE_LANDING_RESOURCE = {
    User.Role.ADMIN: Resource.DASHBOARD,
    User.Role.MODERATOR: Resource.CAMPAIGNS_VIEW,
    User.Role.FINANCE_OFFICER: Resource.CAMPAIGNS_VIEW,
}


def role_has_resource(role: str, resource: str) -> bool:
    return resource in ROLE_RESOURCES.get(role, set())


def user_has_resource(user, resource: str) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff:  # Django staff/superuser escape hatch — separate from the role field
        return True
    return role_has_resource(user.role, resource)
