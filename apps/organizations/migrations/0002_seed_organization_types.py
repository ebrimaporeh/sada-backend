from django.db import migrations

# The 5 pre-existing crowdfunding-eligible types carry over as-is (still
# visible). 'national_agency' is repurposed as "Government Agency" and
# switched to not-visible -- government-institution functionality isn't
# exposed yet, per the launch-phase brief; existing orgs of this type keep
# their data, they just stop being an option for new org creation. NGO/CSO
# are new, crowdfunding-eligible additions. Company is new and not-visible,
# same reasoning as Government Agency.
ORGANIZATION_TYPES = [
    ('religious', 'Religious Organization', True),
    ('student_union', 'Student Union', True),
    ('community', 'Community-Based Organization', True),
    ('media', 'Media Organization', True),
    ('other', 'Other', True),
    ('ngo', 'NGO', True),
    ('cso', 'Civil Society Organization (CSO)', True),
    ('national_agency', 'Government Agency', False),
    ('company', 'Company', False),
]


def seed_organization_types(apps, schema_editor):
    OrganizationType = apps.get_model('organizations', 'OrganizationType')
    for slug, name, is_visible in ORGANIZATION_TYPES:
        OrganizationType.objects.get_or_create(slug=slug, defaults={'name': name, 'is_visible': is_visible})


def unseed_organization_types(apps, schema_editor):
    OrganizationType = apps.get_model('organizations', 'OrganizationType')
    OrganizationType.objects.filter(slug__in=[slug for slug, _, _ in ORGANIZATION_TYPES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('organizations', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_organization_types, unseed_organization_types),
    ]
