from apps.users.models import User, Organization

ORGANIZATIONS_DATA = [
    dict(
        user=dict(
            email='bakau.mosque@example.gm', password='User@1234',
            role=User.Role.USER, account_type=User.AccountType.ORGANIZATION,
            email_verified=True, phone='+220 7300001', region='kanifing',
            bio='Serving the Muslim community of Bakau since 1972.',
        ),
        org=dict(
            organization_name='Bakau Central Mosque Committee',
            organization_type=Organization.OrgType.RELIGIOUS,
            contact_person_name='Alhaji Momodou Jallow',
            phone_2='+220 7300002',
            recovery_email_1='momodou.jallow@example.gm',
        ),
    ),
    dict(
        user=dict(
            email='utgsu@example.gm', password='User@1234',
            role=User.Role.USER, account_type=User.AccountType.ORGANIZATION,
            email_verified=True, phone='+220 7300003', region='brikama',
            bio="The official students' union of the University of The Gambia.",
        ),
        org=dict(
            organization_name="University of The Gambia Students' Union (UTG SU)",
            organization_type=Organization.OrgType.STUDENT_UNION,
            contact_person_name='Fatoumatta Bah',
            phone_2='+220 7300004',
            recovery_email_1='fatoumatta.bah@example.gm',
        ),
    ),
    dict(
        user=dict(
            email='serrekunda.cda@example.gm', password='User@1234',
            role=User.Role.USER, account_type=User.AccountType.ORGANIZATION,
            email_verified=True, phone='+220 7300005', region='kanifing',
            bio='A grassroots community development association serving Greater Serrekunda.',
        ),
        org=dict(
            organization_name='Serrekunda Community Development Association',
            organization_type=Organization.OrgType.COMMUNITY,
            contact_person_name='Isatou Jallow',
            phone_2='+220 7300006',
        ),
    ),
    dict(
        user=dict(
            email='naatip@example.gm', password='User@1234',
            role=User.Role.USER, account_type=User.AccountType.ORGANIZATION,
            email_verified=True, phone='+220 7300007', region='banjul',
            bio='National Agency Against Trafficking in Persons — Government of The Gambia.',
        ),
        org=dict(
            organization_name='National Agency Against Trafficking in Persons (NAATIP)',
            organization_type=Organization.OrgType.NATIONAL_AGENCY,
            contact_person_name='Executive Director\'s Office',
            phone_2='+220 7300008',
            recovery_email_1='info.naatip@example.gm',
            recovery_email_2='director.naatip@example.gm',
        ),
    ),
    dict(
        user=dict(
            email='whatsongambia@example.gm', password='User@1234',
            role=User.Role.USER, account_type=User.AccountType.ORGANIZATION,
            email_verified=True, phone='+220 7300009', region='banjul',
            bio="The Gambia's independent entertainment, culture and events media outlet.",
        ),
        org=dict(
            organization_name="What's On Gambia",
            organization_type=Organization.OrgType.MEDIA,
            contact_person_name='Editorial Team',
            phone_2='+220 7300010',
        ),
    ),
]


def seed_organizations(stdout) -> dict:
    """Creates ORGANIZATIONS_DATA (a User + its Organization profile per
    entry), returns {email: User} for downstream seeders."""
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

        Organization.objects.get_or_create(user=user, defaults=data['org'])
        created[user.email] = user
    return created
