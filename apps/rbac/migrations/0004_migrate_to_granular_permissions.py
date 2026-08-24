from django.db import migrations

# The old flat "can access X" codenames replaced by 0003's granular set,
# mapped to their conservative "_view" equivalent -- the old permission
# never distinguished view from edit/create/delete, so every existing
# grant becomes read-only until an admin explicitly re-grants write access
# on the new checklist. campaigns_view/campaigns_moderate are unchanged
# (already the one existing view/write split) so they're left out of this
# map on purpose.
REMAP = {
    'users': 'users_view',
    'staff': 'staff_view',
    'dashboard': 'dashboard_view',
    'settings': 'settings_edit',
    'categories': 'categories_view',
    'reports': 'reports_view',
    'verifications': 'verifications_view',
    'donations': 'donations_view',
    'finances': 'finances_view',
    'audit': 'audit_view',
}

DEFAULT_ROLES = {
    'moderator': 'Moderator',
    'finance_officer': 'Finance Officer',
}

# Same default grants 0002 always intended (DEFAULT_ROLE_RESOURCES there),
# expressed in the new codenames -- the fallback for a from-scratch
# database (fresh clone, CI, the test suite's in-memory DB). Permission
# rows are only ever created lazily against whatever AdminResource.Meta
# says *right now*, not the schema as of 0002's original authoring, so
# when every migration runs back-to-back against today's code, the old
# flat codenames ('categories', 'reports', ...) never exist as rows at
# all -- there's no real prior grant for the remap below to find or
# convert. On a genuine pre-existing database (one that actually ran
# 0002 back when those codenames existed for real), this fallback never
# fires -- see the has_real_upgrade_data check.
DEFAULT_NEW_RESOURCES = {
    'moderator': ['campaigns_view', 'campaigns_moderate', 'categories_view', 'reports_view', 'verifications_view'],
    'finance_officer': ['campaigns_view', 'donations_view', 'finances_view'],
}


def migrate_forward(apps, schema_editor):
    Permission = apps.get_model('auth', 'Permission')
    Group = apps.get_model('auth', 'Group')
    Role = apps.get_model('rbac', 'Role')

    # Must be checked BEFORE force-creating this migration's own new
    # permission rows below (which would otherwise make it impossible to
    # tell the two cases apart): does this database have any Permission
    # row under one of the truly-renamed old codenames? If yes, it's a
    # real upgrade with real Group grants to preserve. If no, it's a
    # from-scratch database with nothing to remap.
    has_real_upgrade_data = Permission.objects.filter(
        content_type__app_label='rbac', codename__in=list(REMAP.keys()),
    ).exists()

    # Permission rows for 0003's new Meta.permissions are normally created
    # by the post_migrate signal, which only fires once *all* migrations in
    # this `migrate` run have finished -- too late for this data migration
    # to query them. Force creation now (same pattern as 0002).
    from django.apps import apps as django_apps
    from django.contrib.auth.management import create_permissions
    create_permissions(django_apps.get_app_config('rbac'), verbosity=0)

    for slug, name in DEFAULT_ROLES.items():
        Role.objects.get_or_create(slug=slug, defaults={'name': name})

    if has_real_upgrade_data:
        for group in Group.objects.filter(permissions__content_type__app_label='rbac').distinct():
            old_codenames = set(
                group.permissions.filter(content_type__app_label='rbac').values_list('codename', flat=True)
            )
            new_codenames = {REMAP.get(codename, codename) for codename in old_codenames}
            if new_codenames != old_codenames:
                new_perms = list(Permission.objects.filter(content_type__app_label='rbac', codename__in=new_codenames))
                stale_perms = list(group.permissions.filter(content_type__app_label='rbac'))
                group.permissions.remove(*stale_perms)
                group.permissions.add(*new_perms)
    else:
        for slug, codenames in DEFAULT_NEW_RESOURCES.items():
            group, _ = Group.objects.get_or_create(name=slug)
            perms = Permission.objects.filter(content_type__app_label='rbac', codename__in=codenames)
            group.permissions.set(perms)


def migrate_backward(apps, schema_editor):
    # Not meaningfully reversible (which exact old codename a granular one
    # came from is lost once merged) -- the Role rows/schema still roll
    # back fine via 0003's own reversal, this just leaves Group grants as
    # they were on the granular side rather than trying to un-merge them.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('rbac', '0003_role_alter_adminresource_options'),
        ('users', '0015_termsacceptance'),
    ]

    operations = [
        migrations.RunPython(migrate_forward, migrate_backward),
    ]
