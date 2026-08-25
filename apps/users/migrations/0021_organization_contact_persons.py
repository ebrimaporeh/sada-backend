from django.db import migrations, models


class Migration(migrations.Migration):
    """Replaces Organization.contact_person_name (free text) with real
    members flagged via OrganizationMembership.is_contact_person (see
    apps.organizations migration 0003) -- direct removal, no backfill,
    since this field held launch/test data only (confirmed: 1 Organization
    row in the dev db, 0 OrganizationVerification rows -- nothing
    meaningful to carry forward).

    Also drops OrganizationVerification's contact-person ID fields
    (contact_id_type/number/photo_front/photo_back) -- organization
    verification is proof of the org's own registration, not whichever
    member happened to submit the request's personal ID -- and adds
    registration_number, the number printed on the submitted certificate.
    """

    dependencies = [
        ('users', '0020_organization_membership_schema'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='organization',
            name='contact_person_name',
        ),
        migrations.RemoveField(
            model_name='organizationverification',
            name='contact_id_type',
        ),
        migrations.RemoveField(
            model_name='organizationverification',
            name='contact_id_number',
        ),
        migrations.RemoveField(
            model_name='organizationverification',
            name='contact_id_photo_front',
        ),
        migrations.RemoveField(
            model_name='organizationverification',
            name='contact_id_photo_back',
        ),
        migrations.AddField(
            model_name='organizationverification',
            name='registration_number',
            field=models.CharField(default='', max_length=100),
            preserve_default=False,
        ),
    ]
