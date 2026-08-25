import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0008_campaign_admin_notes'),
        ('users', '0020_organization_membership_schema'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaign',
            name='organization',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='campaigns', to='users.organization',
            ),
        ),
    ]
