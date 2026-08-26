from apps.users.models import User, Organization
from apps.organizations.models import OrganizationType, OrganizationRole, OrganizationMembership
from apps.organizations.permissions import ALL_ORGANIZATION_PERMISSIONS
from services.organization_service import OWNER_ROLE_NAME, DEFAULT_MEMBER_ROLE_NAME, DEFAULT_MEMBER_PERMISSIONS

ORGANIZATIONS_DATA = [
    dict(
        user=dict(
            email='bakau.mosque@example.gm', password='User@1234',
            role=User.Role.USER, email_verified=True, phone='+220 7300001', region='kanifing',
            bio='Serving the Muslim community of Bakau since 1972.',
        ),
        org=dict(
            organization_name='Bakau Central Mosque Committee',
            organization_type='religious',
            phone='+220 7300001',
            phone_2='+220 7300002',
            recovery_email_1='momodou.jallow@example.gm',
        ),
    ),
    dict(
        user=dict(
            email='utgsu@example.gm', password='User@1234',
            role=User.Role.USER, email_verified=True, phone='+220 7300003', region='brikama',
            bio="The official students' union of the University of The Gambia.",
        ),
        org=dict(
            organization_name="University of The Gambia Students' Union (UTG SU)",
            organization_type='student_union',
            phone='+220 7300003',
            phone_2='+220 7300004',
            recovery_email_1='fatoumatta.bah@example.gm',
        ),
    ),
    dict(
        user=dict(
            email='serrekunda.cda@example.gm', password='User@1234',
            role=User.Role.USER, email_verified=True, phone='+220 7300005', region='kanifing',
            bio='A grassroots community development association serving Greater Serrekunda.',
        ),
        org=dict(
            organization_name='Serrekunda Community Development Association',
            organization_type='community',
            phone='+220 7300005',
            phone_2='+220 7300006',
        ),
    ),
    dict(
        user=dict(
            email='naatip@example.gm', password='User@1234',
            role=User.Role.USER, email_verified=True, phone='+220 7300007', region='banjul',
            bio='National Agency Against Trafficking in Persons — Government of The Gambia.',
        ),
        org=dict(
            organization_name='National Agency Against Trafficking in Persons (NAATIP)',
            organization_type='national_agency',
            phone='+220 7300007',
            phone_2='+220 7300008',
            recovery_email_1='info.naatip@example.gm',
            recovery_email_2='director.naatip@example.gm',
        ),
    ),
    dict(
        user=dict(
            email='whatsongambia@example.gm', password='User@1234',
            role=User.Role.USER, email_verified=True, phone='+220 7300009', region='banjul',
            bio="The Gambia's independent entertainment, culture and events media outlet.",
        ),
        org=dict(
            organization_name="What's On Gambia",
            organization_type='media',
            phone='+220 7300009',
            phone_2='+220 7300010',
        ),
    ),
]


def seed_organizations(stdout) -> dict:
    """Creates ORGANIZATIONS_DATA (an individual User + an Organization
    they're the Owner-role member of), returns {email: User} for
    downstream seeders -- same contract as before, even though "user" no
    longer means "is this org" the way it did under the old 1:1 model.
    Look up `user.organizations.first()` for the Organization itself."""
    created = {}
    for data in ORGANIZATIONS_DATA:
        user_data = dict(data['user'])
        password = user_data.pop('password')
        user, made = User.objects.get_or_create(email=user_data['email'], defaults=user_data)
        if made:
            user.set_password(password)
            user.save()
            stdout.write(f'  + {user.email}')
        else:
            stdout.write(f'  ~ {user.email} (exists)')

        org_data = dict(data['org'])
        type_slug = org_data.pop('organization_type')
        org_type, _ = OrganizationType.objects.get_or_create(
            slug=type_slug, defaults={'name': type_slug.replace('_', ' ').title()},
        )
        org, org_made = Organization.objects.get_or_create(
            organization_name=org_data['organization_name'],
            defaults={**org_data, 'organization_type': org_type, 'created_by': user},
        )
        if org_made:
            # Not organization_service.create_organization() here -- NAATIP's
            # 'national_agency' type is seeded is_visible=False (government
            # institutions aren't offered at signup this launch), which that
            # function rejects. Mirrors its Owner+Member bootstrapping by
            # hand instead, using the same constants, so every seeded org
            # has a real invitable role, not just an uninvitable Owner.
            owner_role = OrganizationRole.objects.create(
                organization=org, name=OWNER_ROLE_NAME, permissions=list(ALL_ORGANIZATION_PERMISSIONS),
            )
            OrganizationRole.objects.create(
                organization=org, name=DEFAULT_MEMBER_ROLE_NAME, permissions=list(DEFAULT_MEMBER_PERMISSIONS),
            )
            OrganizationMembership.objects.get_or_create(
                user=user, organization=org, defaults={'role': owner_role, 'is_contact_person': True},
            )

        created[user.email] = user
    return created
