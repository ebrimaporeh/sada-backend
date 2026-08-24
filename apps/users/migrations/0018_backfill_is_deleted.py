from django.db import migrations

# Accounts anonymized by _anonymize_account before is_deleted existed have
# no other reliable marker than this email rewrite -- backfill them so the
# fix takes effect for already-deleted accounts, not just future ones.
DELETED_EMAIL_PREFIX = 'deleted-'
DELETED_EMAIL_SUFFIX = '@deleted.sada.gm'


def backfill_is_deleted(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(
        email__startswith=DELETED_EMAIL_PREFIX, email__endswith=DELETED_EMAIL_SUFFIX,
    ).update(is_deleted=True)


def unbackfill_is_deleted(apps, schema_editor):
    User = apps.get_model('users', 'User')
    User.objects.filter(
        email__startswith=DELETED_EMAIL_PREFIX, email__endswith=DELETED_EMAIL_SUFFIX,
    ).update(is_deleted=False)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0017_user_is_deleted'),
    ]

    operations = [
        migrations.RunPython(backfill_is_deleted, unbackfill_is_deleted),
    ]
