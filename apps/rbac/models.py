from django.db import models


class AdminResource(models.Model):
    """No table, no rows -- this model exists purely to anchor the custom
    admin resource permissions below. Django's permission system requires
    every Permission row to be attached to a real model/content type; this
    is that anchor, not something ever queried or instantiated.

    `permissions.roles.Resource` is the single source of truth for the
    resource *keys* used throughout the codebase (view classes'
    `required_resource`, this list, and the frontend mirror) -- if you add
    a resource there, add the matching codename here too, since Django
    permissions have to be declared statically in Meta.
    """
    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ('users', 'Can access Users'),
            ('staff', 'Can access Staff'),
            ('dashboard', 'Can access Dashboard'),
            ('settings', 'Can access Settings'),
            ('campaigns_view', 'Can view Campaigns'),
            ('campaigns_moderate', 'Can moderate Campaigns'),
            ('categories', 'Can access Categories'),
            ('reports', 'Can access Reports'),
            ('verifications', 'Can access Verifications'),
            ('donations', 'Can access Donations'),
            ('finances', 'Can access Finances'),
            ('audit', 'Can access Audit'),
        ]
