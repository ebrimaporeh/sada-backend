from apps.users.models import User

USERS_DATA = [
    # Admin
    dict(
        email='admin@sada.gm', password='Admin@1234',
        first_name='Admin', last_name='Sada',
        role=User.Role.ADMIN, is_staff=True, is_superuser=True,
        email_verified=True, is_verified=True,
        phone='+220 9000000', region='banjul',
        bio='Platform administrator.',
    ),
    # Demo / main user — matches DEMO_USER in mockData.js
    dict(
        email='ousman@sada.gm', password='User@1234',
        first_name='Ousman', last_name='Camara',
        role=User.Role.USER, email_verified=True, is_verified=True,
        phone='+220 7612345', region='banjul',
        bio='Community organizer and fundraising advocate from Banjul.',
    ),
    # Campaign owners
    dict(
        email='omar.jallow@example.gm', password='User@1234',
        first_name='Omar', last_name='Jallow',
        role=User.Role.USER, email_verified=True,
        phone='+220 7100001', region='banjul',
        bio='Healthcare worker and community advocate.',
    ),
    dict(
        email='salimatou.njie@example.gm', password='User@1234',
        first_name='Salimatou', last_name='Njie',
        role=User.Role.USER, email_verified=True,
        phone='+220 7100002', region='brikama',
        bio='Education activist and school committee member.',
    ),
    dict(
        email='isatou.ceesay@example.gm', password='User@1234',
        first_name='Isatou', last_name='Ceesay',
        role=User.Role.USER, email_verified=True,
        phone='+220 7100003', region='basse',
        bio='Relief worker coordinating aid in Upper River Region.',
    ),
    dict(
        email='alhagie.bojang@example.gm', password='User@1234',
        first_name='Alhagie', last_name='Bojang',
        role=User.Role.USER, email_verified=True,
        phone='+220 7100004', region='kanifing',
        bio='Mosque committee member and community leader.',
    ),
    dict(
        email='mariama.sanyang@example.gm', password='User@1234',
        first_name='Mariama', last_name='Sanyang',
        role=User.Role.USER, email_verified=True,
        phone='+220 7100005', region='kerewan',
        bio='Water & sanitation advocate for rural communities.',
    ),
    dict(
        email='lamine.drammeh@example.gm', password='User@1234',
        first_name='Lamine', last_name='Drammeh',
        role=User.Role.USER, email_verified=True,
        phone='+220 7100006', region='kanifing',
        bio='Primary school teacher and father.',
    ),
    dict(
        email='ndey.joof@example.gm', password='User@1234',
        first_name='Ndey', last_name='Joof',
        role=User.Role.USER, email_verified=True,
        phone='+220 7100007', region='banjul',
        bio='Girls education activist and NGO worker.',
    ),
    dict(
        email='gff@example.gm', password='User@1234',
        first_name='GFF', last_name='Media',
        role=User.Role.USER, email_verified=True,
        phone='+220 7100008', region='banjul',
        bio='Official media account of the Gambia Football Federation.',
    ),
    dict(
        email='baboucarr.sowe@example.gm', password='User@1234',
        first_name='Baboucarr', last_name='Sowe',
        role=User.Role.USER, email_verified=True,
        phone='+220 7100009', region='kerewan',
        bio='Solar energy advocate and rural electrification champion.',
    ),
    dict(
        email='fatou.touray@example.gm', password='User@1234',
        first_name='Fatou', last_name='Touray',
        role=User.Role.USER, email_verified=True,
        phone='+220 7100010', region='kanifing',
        bio='Women entrepreneurship leader and cooperative founder.',
    ),
    dict(
        email='amie.saho@example.gm', password='User@1234',
        first_name='Amie', last_name='Saho',
        role=User.Role.USER, email_verified=True,
        phone='+220 7100011', region='banjul',
        bio='Daughter of the late Omar Saho. Keeping his legacy alive.',
    ),
    # Donor-only users
    dict(
        email='aminata.k@example.gm', password='User@1234',
        first_name='Aminata', last_name='Konateh',
        role=User.Role.USER, email_verified=True,
        phone='+220 7200001', region='banjul',
    ),
    dict(
        email='lamine.b@example.gm', password='User@1234',
        first_name='Lamine', last_name='Bojang',
        role=User.Role.USER, email_verified=True,
        phone='+220 7200002', region='kanifing',
    ),
    dict(
        email='kaddy.s@example.gm', password='User@1234',
        first_name='Kaddy', last_name='Sanneh',
        role=User.Role.USER, email_verified=True,
        phone='+220 7200003', region='brikama',
    ),
    dict(
        email='ousman.d@example.gm', password='User@1234',
        first_name='Ousman', last_name='Dibba',
        role=User.Role.USER, email_verified=True,
        phone='+220 7200004', region='kanifing',
    ),
    dict(
        email='modou.t@example.gm', password='User@1234',
        first_name='Modou', last_name='Touray',
        role=User.Role.USER, email_verified=True,
        phone='+220 7200005', region='banjul',
    ),
    dict(
        email='alieu.n@example.gm', password='User@1234',
        first_name='Alieu', last_name='Njie',
        role=User.Role.USER, email_verified=True,
        phone='+220 7200006', region='kanifing',
    ),
]


def seed_users(stdout) -> dict:
    """Creates USERS_DATA, returns {email: User} for downstream seeders."""
    created = {}
    for data in USERS_DATA:
        data = dict(data)
        password = data.pop('password')
        user, made = User.objects.get_or_create(email=data['email'], defaults=data)
        if made:
            user.set_password(password)
            user.save()
            stdout.write(f'  + {user.email}')
        else:
            stdout.write(f'  ~ {user.email} (exists)')
        created[user.email] = user
    return created
