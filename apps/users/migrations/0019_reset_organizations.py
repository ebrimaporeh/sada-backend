from django.db import migrations

# Every existing Organization row (and everything hanging off it) is
# pre-launch dummy/seed data, in production too -- confirmed with the
# project owner, no backfill needed. Wiped outright rather than migrated,
# which is what makes 0020's schema change (old 1:1 fields removed, new
# membership-model fields added as required/non-null straight away) safe
# with no intermediate nullable/rename dance.


def wipe_organizations(apps, schema_editor):
    Organization = apps.get_model('users', 'Organization')
    OrganizationVerification = apps.get_model('users', 'OrganizationVerification')
    OrganizationChangeRequest = apps.get_model('users', 'OrganizationChangeRequest')
    User = apps.get_model('users', 'User')

    OrganizationChangeRequest.objects.all().delete()
    OrganizationVerification.objects.all().delete()
    Organization.objects.all().delete()
    # The underlying User rows (e.g. bakau.mosque@example.gm) survive --
    # only their Organization profile is dummy data. account_type is
    # vestigial now regardless (see User.AccountType), but reset for
    # cleanliness rather than leaving it stuck on a value that no longer
    # corresponds to an Organization row.
    User.objects.filter(account_type='organization').update(account_type='individual')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0018_backfill_is_deleted'),
    ]

    operations = [
        migrations.RunPython(wipe_organizations, noop_reverse),
    ]
