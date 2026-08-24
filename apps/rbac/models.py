from django.db import models
from apps.core.models import BaseModel


class AdminResource(models.Model):
    """No table, no rows -- this model exists purely to anchor the custom
    admin resource permissions below. Django's permission system requires
    every Permission row to be attached to a real model/content type; this
    is that anchor, not something ever queried or instantiated.

    `permissions.roles.Resource` is the single source of truth for the
    resource *keys* used throughout the codebase (view classes'
    `required_resource`/`resource_by_method`, this list, and the frontend
    mirror) -- if you add a resource there, add the matching codename here
    too, since Django permissions have to be declared statically in Meta.

    Codenames are `<entity>_<action>` (view/create/edit/delete), except
    for the handful of entities that only ever expose one real action --
    inventing e.g. a "create" checkbox for a read-only analytics screen
    would be a permission nobody's code ever checks, which is worse than
    not having it.
    """
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ('users_view', 'Can view Users'),
            ('users_edit', 'Can edit Users'),
            ('users_delete', 'Can delete Users'),
            ('staff_view', 'Can view Staff'),
            ('staff_create', 'Can create Staff'),
            ('staff_edit', 'Can edit Staff'),
            ('staff_delete', 'Can delete Staff'),
            ('roles_manage', 'Can manage Roles & Permissions'),
            ('dashboard_view', 'Can view Dashboard'),
            ('settings_edit', 'Can edit Settings'),
            ('campaigns_view', 'Can view Campaigns'),
            ('campaigns_moderate', 'Can moderate Campaigns'),
            ('categories_view', 'Can view Categories'),
            ('categories_create', 'Can create Categories'),
            ('categories_edit', 'Can edit Categories'),
            ('categories_delete', 'Can delete Categories'),
            ('reports_view', 'Can view Reports'),
            ('reports_edit', 'Can edit Reports'),
            ('verifications_view', 'Can view Verifications'),
            ('verifications_edit', 'Can edit Verifications'),
            ('donations_view', 'Can view Donations'),
            ('donations_edit', 'Can edit Donations'),
            ('finances_view', 'Can view Finances'),
            ('audit_view', 'Can view Audit'),
        ]


class Role(BaseModel):
    """A runtime-defined staff role -- one row per role an admin can assign
    and edit permissions for, 1:1 with a Django Group of the same `slug`
    (see permissions/roles.py, which does the actual Group/Permission
    read-write). Replaces the old hardcoded `MANAGED_ROLES` tuple: Admin
    creates a row here (via the Roles & Permissions screen) instead of a
    role only existing if it was hand-written into the codebase.

    Deliberately doesn't cover `admin`/`user`/`premium` -- those are fixed
    `User.Role` values with meaning outside the resource-permission system
    (Admin's unconditional full-access escape hatch, Premium's donation
    perks) and aren't "a bag of resource grants" the way a staff role is.
    """
    slug = models.SlugField(max_length=30, unique=True)
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Role'
        verbose_name_plural = 'Roles'

    def __str__(self):
        return self.name
