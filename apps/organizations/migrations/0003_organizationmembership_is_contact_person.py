from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0002_seed_organization_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizationmembership',
            name='is_contact_person',
            field=models.BooleanField(default=False),
        ),
    ]
