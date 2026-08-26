import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Organization stops being 1:1 with User -- safe as a direct schema
    change (no intermediate temp fields/backfill) because 0019 already
    wiped every existing row that would otherwise need migrating."""

    dependencies = [
        ('users', '0019_reset_organizations'),
        ('organizations', '0002_seed_organization_types'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='organization',
            name='user',
        ),
        migrations.RemoveField(
            model_name='organization',
            name='organization_type',
        ),
        migrations.AddField(
            model_name='organization',
            name='organization_type',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='organizations', to='organizations.organizationtype',
            ),
        ),
        migrations.AddField(
            model_name='organization',
            name='created_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_organizations', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='organization',
            name='phone',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='organization',
            name='is_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.RenameField(
            model_name='organizationverification',
            old_name='user',
            new_name='submitted_by',
        ),
        migrations.AddField(
            model_name='organizationverification',
            name='organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='verification_requests', to='users.organization',
            ),
        ),
        migrations.RenameField(
            model_name='organizationchangerequest',
            old_name='user',
            new_name='submitted_by',
        ),
        migrations.AddField(
            model_name='organizationchangerequest',
            name='organization',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='change_requests', to='users.organization',
            ),
        ),
    ]
