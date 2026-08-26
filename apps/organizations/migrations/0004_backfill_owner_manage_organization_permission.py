from django.db import migrations

# manage_organization is a new OrganizationPermission value (see
# apps.organizations.permissions) that gates editing an org's own profile
# fields (phone/recovery emails, via OrganizationChangeRequest) -- previously
# ungated for any member, see services/organization_change_service.py's
# submit_change_request(). New orgs' Owner role picks this up automatically
# via ALL_ORGANIZATION_PERMISSIONS (organization_service.create_organization),
# but every *existing* Owner role's `permissions` JSONField was snapshotted
# at creation time and won't include it without this backfill. Member/custom
# roles are deliberately left untouched -- an owner can grant this
# permission to a trusted role afterward via the existing Roles UI.
OWNER_ROLE_NAME = 'Owner'
MANAGE_ORGANIZATION = 'manage_organization'


def backfill_manage_organization(apps, schema_editor):
    OrganizationRole = apps.get_model('organizations', 'OrganizationRole')
    for role in OrganizationRole.objects.filter(name=OWNER_ROLE_NAME):
        if MANAGE_ORGANIZATION not in role.permissions:
            role.permissions = [*role.permissions, MANAGE_ORGANIZATION]
            role.save(update_fields=['permissions'])


def remove_manage_organization(apps, schema_editor):
    OrganizationRole = apps.get_model('organizations', 'OrganizationRole')
    for role in OrganizationRole.objects.filter(name=OWNER_ROLE_NAME):
        if MANAGE_ORGANIZATION in role.permissions:
            role.permissions = [p for p in role.permissions if p != MANAGE_ORGANIZATION]
            role.save(update_fields=['permissions'])


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0003_organizationmembership_is_contact_person'),
    ]

    operations = [
        migrations.RunPython(backfill_manage_organization, remove_manage_organization),
    ]
