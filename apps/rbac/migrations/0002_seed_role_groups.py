from django.db import migrations

# Same access moderator/finance_officer had under the old hardcoded
# ROLE_RESOURCES dict (permissions/roles.py, pre-Django-Groups) — seeded
# here so switching to admin-editable Groups doesn't change anyone's
# access until an admin actually edits something on the Staff page.
DEFAULT_ROLE_RESOURCES = {
    'moderator': ['campaigns_view', 'campaigns_moderate', 'categories', 'reports', 'verifications'],
    'finance_officer': ['campaigns_view', 'donations', 'finances'],
}


def seed_role_groups(apps, schema_editor):
    # Permission rows for a just-created model's Meta.permissions are
    # normally created by the post_migrate signal, which only fires once
    # *all* migrations in this `migrate` run have finished — too late for
    # a data migration in the same run to query them. Force creation now.
    from django.apps import apps as django_apps
    from django.contrib.auth.management import create_permissions
    app_config = django_apps.get_app_config('rbac')
    create_permissions(app_config, verbosity=0)

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    User = apps.get_model('users', 'User')

    for role, codenames in DEFAULT_ROLE_RESOURCES.items():
        group, _ = Group.objects.get_or_create(name=role)
        perms = Permission.objects.filter(content_type__app_label='rbac', codename__in=codenames)
        group.permissions.set(perms)
        for user in User.objects.filter(role=role):
            user.groups.add(group)


def unseed_role_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=DEFAULT_ROLE_RESOURCES.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('rbac', '0001_initial'),
        ('users', '0015_termsacceptance'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(seed_role_groups, unseed_role_groups),
    ]
