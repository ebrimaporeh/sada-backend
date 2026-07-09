from decimal import Decimal
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from apps.users.models import User


class Command(BaseCommand):
    help = 'Seed the database with realistic Sada data'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Clear all data before seeding')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['clear']:
            self._clear()

        from apps.campaigns.models import Category
        if not options['clear'] and Category.objects.exists():
            self.stdout.write(self.style.WARNING('Database already seeded — skipping. Use --clear to reseed.'))
            return

        self.stdout.write('Seeding users...')
        users = self._seed_users()

        self.stdout.write('Seeding categories...')
        cats = self._seed_categories()

        self.stdout.write('Seeding campaigns...')
        campaigns = self._seed_campaigns(users, cats)

        self.stdout.write('Seeding campaign updates...')
        self._seed_updates(campaigns, users)

        self.stdout.write('Seeding donations...')
        self._seed_donations(campaigns, users)

        self.stdout.write('Seeding payouts...')
        self._seed_payouts(campaigns, users)

        self.stdout.write(self.style.SUCCESS('\nDatabase seeded successfully.'))
        self._print_summary(users, cats, campaigns)

    # ─── Clear ───────────────────────────────────────────────────────────────

    def _clear(self):
        self.stdout.write(self.style.WARNING('Clearing existing data...'))
        from apps.payments.models import Payout, Payment
        from apps.donations.models import Donation
        from apps.campaigns.models import Campaign, Category, CampaignUpdate, CampaignImage
        from apps.notifications.models import Notification
        Notification.objects.all().delete()
        Payout.objects.all().delete()
        Payment.objects.all().delete()
        Donation.objects.all().delete()
        CampaignUpdate.objects.all().delete()
        CampaignImage.objects.all().delete()
        Campaign.objects.all().delete()
        Category.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        self.stdout.write('  Done.')

    # ─── Users ───────────────────────────────────────────────────────────────

    def _seed_users(self):
        users_data = [
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

        created = {}
        for data in users_data:
            password = data.pop('password')
            user, made = User.objects.get_or_create(email=data['email'], defaults=data)
            if made:
                user.set_password(password)
                user.save()
                self.stdout.write(f'  + {user.email}')
            else:
                self.stdout.write(f'  ~ {user.email} (exists)')
            created[user.email] = user
        return created

    # ─── Categories ──────────────────────────────────────────────────────────

    def _seed_categories(self):
        cats_data = [
            dict(name='Medical & Health',    slug='medical',    icon='heart',     description='Medical bills, surgeries, and health emergencies.'),
            dict(name='Education',           slug='education',  icon='book',      description='School fees, scholarships, and educational needs.'),
            dict(name='Business',            slug='business',   icon='briefcase', description='Small business start-ups and livelihood support.'),
            dict(name='Religious',           slug='religious',  icon='moon',      description='Mosques, churches, and places of worship.'),
            dict(name='Community Projects',  slug='community',  icon='users',     description='Local community development and infrastructure.'),
            dict(name='Disaster Relief',     slug='disaster',   icon='alert',     description='Floods, fires, and urgent emergencies.'),
            dict(name='Youth & Sports',      slug='sports',     icon='zap',       description='Youth development, sports, and fitness.'),
            dict(name='Memorial',            slug='memorial',   icon='star',      description='Honouring loved ones and keeping legacies alive.'),
            dict(name='Charity',             slug='charity',    icon='gift',      description='General charitable causes and giving.'),
            dict(name='Agriculture & Food',  slug='agriculture',icon='leaf',      description='Farming, food security, and rural livelihoods.'),
            dict(name='Women & Girls',       slug='women',      icon='award',     description='Empowering women and girls across The Gambia.'),
            dict(name='Other',               slug='other',      icon='more',      description='Other causes not listed above.'),
        ]
        from apps.campaigns.models import Category
        created = {}
        for data in cats_data:
            obj, made = Category.objects.get_or_create(slug=data['slug'], defaults=data)
            if made:
                self.stdout.write(f'  + {obj.name}')
            created[obj.slug] = obj
        return created

    # ─── Campaigns ───────────────────────────────────────────────────────────

    def _seed_campaigns(self, users, cats):
        from apps.campaigns.models import Campaign

        today = date.today()
        U = users  # shorthand

        campaigns_data = [
            dict(
                slug='help-fatou-get-kidney-surgery',
                owner=U.get('omar.jallow@example.gm'),
                category=cats.get('medical'),
                title='Help Fatou Get Kidney Surgery',
                short_description='Fatou Jallow, 34, urgently needs kidney surgery at RVTH. She is a mother of two and cannot afford the full cost of treatment.',
                story="""Fatou Jallow is a 34-year-old mother of two young children living in Banjul. Three months ago, she was diagnosed with chronic kidney disease requiring immediate surgery at the Royal Victoria Teaching Hospital (RVTH).

Without this surgery, Fatou's condition will continue to deteriorate. Her husband works as a groundnut farmer and the family's income is not enough to cover the medical costs.

The total cost of the surgery and post-operative care is D 150,000. We are asking for your support to help Fatou get the medical treatment she desperately needs.

Any amount helps. Please share this campaign with your network. Together, we can give Fatou a second chance at life with her family.""",
                goal=Decimal('150000.00'), raised=Decimal('112500.00'), donors_count=187,
                deadline=today + timedelta(days=40), status=Campaign.Status.ACTIVE,
                region='banjul', beneficiary='Fatou Jallow', beneficiary_relationship='Self',
                is_urgent=True, is_featured=True,
                approved_at=timezone.now() - timedelta(days=35),
            ),
            dict(
                slug='brikama-school-building-project',
                owner=U.get('salimatou.njie@example.gm'),
                category=cats.get('education'),
                title='Build a New Classroom Block in Brikama',
                short_description='Over 400 students at Brikama Primary School are learning in overcrowded classrooms. Help us build 6 new classrooms.',
                story="""Brikama Primary School serves over 400 students in the West Coast Region, but its aging infrastructure can no longer accommodate the growing student population.

Students are sharing textbooks, sitting on the floor, and classes are being held in shifts because there isn't enough space. During the rainy season, the situation becomes dangerous as the old roof leaks.

We are raising funds to construct 6 new classrooms, install desks and chairs, and repair the existing roof. The total project cost is D 500,000.

This project is supported by the local school committee, parents association, and the regional education office.""",
                goal=Decimal('500000.00'), raised=Decimal('342000.00'), donors_count=412,
                deadline=today + timedelta(days=88), status=Campaign.Status.ACTIVE,
                region='brikama', beneficiary='Brikama Primary School', beneficiary_relationship='Community Institution',
                is_urgent=False, is_featured=True,
                approved_at=timezone.now() - timedelta(days=87),
            ),
            dict(
                slug='flood-relief-basse-2026',
                owner=U.get('isatou.ceesay@example.gm'),
                category=cats.get('disaster'),
                title='Flood Relief Fund — Basse 2026',
                short_description='Flash floods in Basse Santa Su have displaced over 2,000 families. Help us provide emergency food, shelter and clean water.',
                story="""On May 12th, 2026, severe flash floods devastated Basse Santa Su in the Upper River Region. Over 2,000 families were displaced overnight, losing their homes, livestock, and food supplies.

The immediate needs are:
- Emergency shelter tents
- Clean drinking water
- Food packages for displaced families
- Medical supplies for injuries and waterborne disease prevention

Our team is on the ground coordinating relief efforts with local authorities. Every donation goes directly toward emergency supplies for affected families.

Please give generously and share this campaign widely. Lives depend on it.""",
                goal=Decimal('1000000.00'), raised=Decimal('834000.00'), donors_count=1243,
                deadline=today + timedelta(days=25), status=Campaign.Status.ACTIVE,
                region='basse', beneficiary='Flood Victims — Basse Santa Su', beneficiary_relationship='Community',
                is_urgent=True, is_featured=True,
                approved_at=timezone.now() - timedelta(days=23),
            ),
            dict(
                slug='bakau-mosque-renovation',
                owner=U.get('alhagie.bojang@example.gm'),
                category=cats.get('religious'),
                title='Renovate the Bakau Central Mosque',
                short_description='The Bakau Central Mosque, built in 1972, needs urgent renovation. Help restore this important place of worship for the entire community.',
                story="""The Bakau Central Mosque has been serving the Muslim community of Bakau for over 50 years. However, decades of use have left the mosque in need of significant repairs.

The renovation project includes:
- Roof repair and waterproofing
- New wudu (ablution) facilities
- Electrical wiring and lighting
- Flooring restoration
- New sound system

The renovation work will be carried out by local Gambian contractors. All funds are overseen by the mosque management committee.""",
                goal=Decimal('300000.00'), raised=Decimal('278000.00'), donors_count=389,
                deadline=today + timedelta(days=76), status=Campaign.Status.ACTIVE,
                region='kanifing', beneficiary='Bakau Central Mosque', beneficiary_relationship='Religious Institution',
                is_urgent=False, is_featured=False,
                approved_at=timezone.now() - timedelta(days=111),
            ),
            dict(
                slug='farafenni-clean-water-project',
                owner=U.get('mariama.sanyang@example.gm'),
                category=cats.get('community'),
                title='Clean Water for Farafenni North Ward',
                short_description='Residents of Farafenni North Ward walk 3km daily for clean water. Help us install a community borehole and water distribution system.',
                story="""Over 800 families in Farafenni North Ward have no access to clean piped water. Women and children walk up to 3 kilometers daily to fetch water from a shared well that often dries up in the dry season.

This campaign will fund the installation of a deep borehole with a solar-powered pump and a distribution system connecting 15 community standpipes.

The project is partnered with the North Bank Region Water Authority and will be maintained by a democratically elected community water committee.

Clean water changes everything — health, school attendance, women's time, and community prosperity.""",
                goal=Decimal('450000.00'), raised=Decimal('198000.00'), donors_count=276,
                deadline=today + timedelta(days=147), status=Campaign.Status.ACTIVE,
                region='kerewan', beneficiary='Farafenni North Ward Community', beneficiary_relationship='Community',
                is_urgent=False, is_featured=False,
                approved_at=timezone.now() - timedelta(days=65),
            ),
            dict(
                slug='baby-modou-heart-surgery',
                owner=U.get('lamine.drammeh@example.gm'),
                category=cats.get('medical'),
                title='Baby Modou Needs Heart Surgery',
                short_description='Modou is only 8 months old and was born with a congenital heart defect. His family needs help to fund life-saving surgery in Senegal.',
                story="""Baby Modou Drammeh was born with a congenital ventricular septal defect (VSD) — a hole in the heart. Without surgery, doctors say he will not survive past two years.

The surgery can be performed at Hôpital Principal in Dakar, Senegal, but the total cost including transport, surgery, and recovery care is D 250,000.

Modou's father is a primary school teacher and his mother stays home to care for him. They simply cannot afford this cost on their own.

Please help give baby Modou a chance to live, grow up, and thrive. Share this campaign with everyone you know.""",
                goal=Decimal('250000.00'), raised=Decimal('156000.00'), donors_count=298,
                deadline=today + timedelta(days=26), status=Campaign.Status.ACTIVE,
                region='kanifing', beneficiary='Modou Drammeh', beneficiary_relationship='Son',
                is_urgent=True, is_featured=False,
                approved_at=timezone.now() - timedelta(days=30),
            ),
            dict(
                slug='girls-scholarship-fund-gambia',
                owner=U.get('ndey.joof@example.gm'),
                category=cats.get('education'),
                title='Girls Scholarship Fund 2026',
                short_description='Provide full secondary school scholarships to 20 talented girls from rural Gambia whose families cannot afford school fees.',
                story="""Despite recent progress, many talented girls in rural Gambia are forced to drop out of secondary school because their families cannot afford the fees, uniforms, and supplies.

This scholarship fund will cover one full academic year for 20 girls from the North Bank, Upper River, and Central River Regions — including school fees, uniforms, books, and a monthly transport stipend.

Scholars are selected based on academic performance and financial need, in partnership with regional education offices and community leaders.

Education is the most powerful investment we can make in The Gambia's future.""",
                goal=Decimal('600000.00'), raised=Decimal('425000.00'), donors_count=534,
                deadline=today + timedelta(days=71), status=Campaign.Status.ACTIVE,
                region='banjul', beneficiary='20 Rural Girls', beneficiary_relationship='Scholarship Recipients',
                is_urgent=False, is_featured=False,
                approved_at=timezone.now() - timedelta(days=77),
            ),
            dict(
                slug='gambia-u17-football-afcon',
                owner=U.get('gff@example.gm'),
                category=cats.get('sports'),
                title='Scorpions U17 — Road to AFCON',
                short_description='Help The Gambia U17 national football team travel to and compete at the Africa U17 Cup of Nations in Abidjan.',
                story="""The Gambia U17 national football team has qualified for the Africa U17 Cup of Nations (AFCON) in Côte d'Ivoire — a remarkable achievement for our small nation!

However, the Gambia Football Federation needs additional funds to cover travel, accommodation, training camp, and equipment for the squad.

Let's rally behind our Scorpions! Every donation brings these young players one step closer to representing The Gambia on the continental stage.

Once a Scorpion, always a Scorpion!""",
                goal=Decimal('150000.00'), raised=Decimal('89000.00'), donors_count=1567,
                deadline=today + timedelta(days=55), status=Campaign.Status.ACTIVE,
                region='banjul', beneficiary='Gambia Football Federation', beneficiary_relationship='National Sports Body',
                is_urgent=False, is_featured=False,
                approved_at=timezone.now() - timedelta(days=51),
            ),
            dict(
                slug='solar-panels-jinack-village-school',
                owner=U.get('baboucarr.sowe@example.gm'),
                category=cats.get('community'),
                title='Solar Panels for Jinack Village School',
                short_description='Jinack Island school has no electricity. Solar panels will allow evening study classes for 250 students and power computers.',
                story="""Jinack Island is a remote community accessible only by boat. The village school serves 250 students, but without electricity, children cannot study after dark and the school cannot run computer classes.

Installing a solar panel system will:
- Provide reliable electricity for classrooms and the library
- Enable computer-based learning for the first time
- Allow evening study sessions during exam periods
- Power the water pump and cooling fans

The system will be installed by a certified Gambian solar technician and maintained by trained community members.""",
                goal=Decimal('350000.00'), raised=Decimal('290000.00'), donors_count=342,
                deadline=today + timedelta(days=102), status=Campaign.Status.ACTIVE,
                region='kerewan', beneficiary='Jinack Village School', beneficiary_relationship='Community School',
                is_urgent=False, is_featured=False,
                approved_at=timezone.now() - timedelta(days=67),
            ),
            dict(
                slug='kanifing-market-expansion',
                owner=U.get('fatou.touray@example.gm'),
                category=cats.get('women'),
                title="Expand Kanifing Women's Market",
                short_description='Help 50 women entrepreneurs in Kanifing expand their market stalls and access microfinance to grow their small businesses.',
                story="""The Kanifing Women's Market Cooperative has been empowering female entrepreneurs since 2018. With 50 active members selling produce, textiles, and crafts, the cooperative has outgrown its current space.

This campaign will fund:
- Construction of 15 new market stalls
- Purchase of cold storage equipment for perishable goods
- A revolving microfinance fund accessible to all members
- Business skills training workshop

All project management and accounting is handled transparently by the cooperative's elected board.""",
                goal=Decimal('200000.00'), raised=Decimal('67000.00'), donors_count=89,
                deadline=today + timedelta(days=178), status=Campaign.Status.ACTIVE,
                region='kanifing', beneficiary="Kanifing Women's Cooperative", beneficiary_relationship='Community Organization',
                is_urgent=False, is_featured=False,
                approved_at=timezone.now() - timedelta(days=34),
            ),
            dict(
                slug='memorial-late-omar-saho',
                owner=U.get('amie.saho@example.gm'),
                category=cats.get('memorial'),
                title='Memorial Garden for Late Omar Saho',
                short_description='Create a memorial garden and scholarship in memory of beloved teacher Omar Saho, who passed away in April 2026.',
                story="""Omar Saho dedicated 30 years of his life to teaching at Banjul Senior Secondary School. He was beloved by thousands of students, a mentor, and a community pillar.

In his memory, his family and former students wish to:
- Create a memorial garden at the school bearing his name
- Establish an annual scholarship for a deserving student in his name
- Commission a small plaque in his honor in the school library

Omar always said: "Education is the candle that lights the darkness." Let's keep that candle burning.""",
                goal=Decimal('100000.00'), raised=Decimal('87500.00'), donors_count=412,
                deadline=today + timedelta(days=57), status=Campaign.Status.ACTIVE,
                region='banjul', beneficiary='Saho Family', beneficiary_relationship='Family',
                is_urgent=False, is_featured=False,
                approved_at=timezone.now() - timedelta(days=46),
            ),
            dict(
                slug='gambia-tech-hub-banjul',
                owner=U.get('ousman@sada.gm'),
                category=cats.get('business'),
                title="Launch Gambia's First Free Coding Bootcamp",
                short_description='Train 100 young Gambians in software development, data science and digital skills — completely free.',
                story="""The Gambia has incredible young talent, but limited access to quality tech education. We are launching a 6-month intensive coding bootcamp in Banjul for 100 young Gambians aged 18-28.

The curriculum covers:
- Web development (React, Django)
- Mobile development
- Data science and AI basics
- Digital entrepreneurship and freelancing

Graduates will receive placement support, mentorship from Gambian tech professionals abroad, and access to our startup incubator.

The course is completely free for students. All they need is the determination to learn.""",
                goal=Decimal('800000.00'), raised=Decimal('312000.00'), donors_count=234,
                deadline=today + timedelta(days=118), status=Campaign.Status.ACTIVE,
                region='banjul', beneficiary='100 Young Gambians', beneficiary_relationship='Students',
                is_urgent=False, is_featured=False,
                approved_at=timezone.now() - timedelta(days=56),
            ),
        ]

        created = {}
        for data in campaigns_data:
            slug = data['slug']
            if not Campaign.objects.filter(slug=slug).exists():
                Campaign.objects.create(**data)
                self.stdout.write(f'  + {data["title"][:55]}')
            else:
                self.stdout.write(f'  ~ {data["title"][:55]} (exists)')
            created[slug] = Campaign.objects.get(slug=slug)
        return created

    # ─── Campaign Updates ────────────────────────────────────────────────────

    def _seed_updates(self, campaigns, users):
        from apps.campaigns.models import CampaignUpdate

        updates = [
            dict(
                campaign=campaigns.get('help-fatou-get-kidney-surgery'),
                posted_by=users.get('omar.jallow@example.gm'),
                title='Surgery scheduled!',
                content='Great news! The hospital has confirmed a surgery date for July 8th. Thank you all for your incredible support. The medical team is optimistic about the outcome.',
            ),
            dict(
                campaign=campaigns.get('help-fatou-get-kidney-surgery'),
                posted_by=users.get('omar.jallow@example.gm'),
                title='Update from the doctors',
                content="The medical team has reviewed Fatou's case in detail. They are optimistic about the outcome of the surgery. Please continue to share this campaign — we need to reach D150,000 before the surgery date.",
            ),
            dict(
                campaign=campaigns.get('brikama-school-building-project'),
                posted_by=users.get('salimatou.njie@example.gm'),
                title='Foundation work started!',
                content='The construction team has broken ground. Foundation work is now underway thanks to your generous donations. We expect the walls to go up next week.',
            ),
            dict(
                campaign=campaigns.get('brikama-school-building-project'),
                posted_by=users.get('salimatou.njie@example.gm'),
                title='Materials purchased',
                content='We have purchased cement, steel rods, and sand for the first three classrooms. The regional education office has also pledged to donate 200 desks once construction is complete.',
            ),
            dict(
                campaign=campaigns.get('flood-relief-basse-2026'),
                posted_by=users.get('isatou.ceesay@example.gm'),
                title='First relief convoy dispatched',
                content='We have dispatched the first convoy of relief supplies to Basse — 500 food packages, 150 shelter tents, and 2,000 litres of clean water. Thank you for making this possible.',
            ),
            dict(
                campaign=campaigns.get('girls-scholarship-fund-gambia'),
                posted_by=users.get('ndey.joof@example.gm'),
                title='First 10 scholars selected!',
                content='We are thrilled to announce that the first 10 scholarship recipients have been selected. These remarkable young women will start their academic year in September. Meet them on our website.',
            ),
            dict(
                campaign=campaigns.get('gambia-tech-hub-banjul'),
                posted_by=users.get('ousman@sada.gm'),
                title='Venue secured in Banjul',
                content='We have signed the lease for our bootcamp venue on Kairaba Avenue. The space will accommodate 50 students per cohort. Equipment procurement starts next week.',
            ),
        ]

        for data in updates:
            if data['campaign'] and not CampaignUpdate.objects.filter(
                campaign=data['campaign'], title=data['title']
            ).exists():
                CampaignUpdate.objects.create(**data)
                self.stdout.write(f'  + Update: {data["title"]}')

    # ─── Donations ───────────────────────────────────────────────────────────

    def _seed_donations(self, campaigns, users):
        from apps.donations.models import Donation
        import uuid

        def make_ref():
            return f'GF-{uuid.uuid4().hex[:12].upper()}'

        now = timezone.now()

        donations = [
            # Campaign 1: Help Fatou
            dict(campaign='help-fatou-get-kidney-surgery', donor='aminata.k@example.gm',   amount=500,   msg='Praying for your recovery, Fatou!',         anon=False, days_ago=0,  phone='+220 7200001'),
            dict(campaign='help-fatou-get-kidney-surgery', donor=None,                      amount=2500,  msg='',                                          anon=True,  days_ago=0,  phone='+220 7999001'),
            dict(campaign='help-fatou-get-kidney-surgery', donor='lamine.b@example.gm',    amount=1000,  msg='Stay strong! From the diaspora with love.', anon=False, days_ago=1,  phone='+220 7200002'),
            dict(campaign='help-fatou-get-kidney-surgery', donor='kaddy.s@example.gm',     amount=250,   msg='Small contribution but big prayers.',       anon=False, days_ago=1,  phone='+220 7200003'),
            dict(campaign='help-fatou-get-kidney-surgery', donor='ousman.d@example.gm',    amount=5000,  msg='A donation from our family in Sweden.',     anon=False, days_ago=1,  phone='+220 7200004'),
            dict(campaign='help-fatou-get-kidney-surgery', donor=None,                      amount=100,   msg='',                                          anon=True,  days_ago=1,  phone='+220 7999002'),
            dict(campaign='help-fatou-get-kidney-surgery', donor='fatou.touray@example.gm',amount=750,   msg='We see you. Keep fighting!',               anon=False, days_ago=2,  phone='+220 7100010'),
            dict(campaign='help-fatou-get-kidney-surgery', donor='lamine.drammeh@example.gm',amount=300, msg='',                                          anon=False, days_ago=2,  phone='+220 7100006'),
            dict(campaign='help-fatou-get-kidney-surgery', donor='mariama.sanyang@example.gm',amount=1500,msg="From our women's group in Serrekunda.",    anon=False, days_ago=3,  phone='+220 7100005'),
            dict(campaign='help-fatou-get-kidney-surgery', donor=None,                      amount=5000,  msg='',                                          anon=True,  days_ago=4,  phone='+220 7999003'),
            dict(campaign='help-fatou-get-kidney-surgery', donor='baboucarr.sowe@example.gm',amount=200, msg='Get well soon Fatou!',                      anon=False, days_ago=5,  phone='+220 7100009'),
            dict(campaign='help-fatou-get-kidney-surgery', donor='ndey.joof@example.gm',   amount=2000,  msg='Sending love from London.',                 anon=False, days_ago=6,  phone='+220 7100007'),
            # Campaign 2: Brikama School
            dict(campaign='brikama-school-building-project', donor='ousman@sada.gm',  amount=10000, msg='Building The Gambia one classroom at a time!',anon=False,days_ago=2, phone='+220 7612345'),
            dict(campaign='brikama-school-building-project', donor='aminata.k@example.gm',  amount=500,   msg='',                                           anon=False,days_ago=3, phone='+220 7200001'),
            dict(campaign='brikama-school-building-project', donor=None,                     amount=5000,  msg='',                                           anon=True, days_ago=5, phone='+220 7999004'),
            dict(campaign='brikama-school-building-project', donor='alieu.n@example.gm',    amount=2500,  msg='Support our children.',                      anon=False,days_ago=7, phone='+220 7200006'),
            # Campaign 3: Flood Relief
            dict(campaign='flood-relief-basse-2026', donor='ousman@sada.gm',           amount=20000, msg='Sending hope to Basse.',                    anon=False,days_ago=0, phone='+220 7612345'),
            dict(campaign='flood-relief-basse-2026', donor=None,                              amount=50000, msg='',                                          anon=True, days_ago=1, phone='+220 7999005'),
            dict(campaign='flood-relief-basse-2026', donor='modou.t@example.gm',             amount=5000,  msg='Stay strong Basse!',                        anon=False,days_ago=2, phone='+220 7200005'),
            dict(campaign='flood-relief-basse-2026', donor='alieu.n@example.gm',             amount=3000,  msg='',                                          anon=False,days_ago=3, phone='+220 7200006'),
            # Campaign 6: Baby Modou
            dict(campaign='baby-modou-heart-surgery', donor='aminata.k@example.gm',          amount=1000,  msg='God bless baby Modou.',                     anon=False,days_ago=1, phone='+220 7200001'),
            dict(campaign='baby-modou-heart-surgery', donor=None,                             amount=5000,  msg='',                                          anon=True, days_ago=2, phone='+220 7999006'),
            dict(campaign='baby-modou-heart-surgery', donor='ousman@sada.gm',           amount=10000, msg='Praying for a full recovery.',              anon=False,days_ago=3, phone='+220 7612345'),
            # Campaign 7: Girls Scholarship
            dict(campaign='girls-scholarship-fund-gambia', donor='ousman@sada.gm',      amount=15000, msg='Educate a girl, transform a nation.',       anon=False,days_ago=1, phone='+220 7612345'),
            dict(campaign='girls-scholarship-fund-gambia', donor='modou.t@example.gm',        amount=5000,  msg='',                                          anon=False,days_ago=4, phone='+220 7200005'),
            dict(campaign='girls-scholarship-fund-gambia', donor=None,                         amount=25000, msg='',                                          anon=True, days_ago=6, phone='+220 7999007'),
            # Campaign 12: Tech Hub
            dict(campaign='gambia-tech-hub-banjul', donor='modou.t@example.gm',               amount=5000,  msg="Investing in Gambia's future!",             anon=False,days_ago=1, phone='+220 7200005'),
            dict(campaign='gambia-tech-hub-banjul', donor=None,                                amount=10000, msg='',                                          anon=True, days_ago=2, phone='+220 7999008'),
            dict(campaign='gambia-tech-hub-banjul', donor='alieu.n@example.gm',               amount=1000,  msg='I wish I had this when I was starting out.',anon=False,days_ago=4, phone='+220 7200006'),
            dict(campaign='gambia-tech-hub-banjul', donor='aminata.k@example.gm',             amount=2500,  msg='Train our girls in tech too!',              anon=False,days_ago=5, phone='+220 7200001'),
            dict(campaign='gambia-tech-hub-banjul', donor=None,                                amount=7500,  msg='',                                          anon=True, days_ago=7, phone='+220 7999009'),
        ]

        fee_rate = Decimal('0.015')
        count = 0
        for row in donations:
            campaign = campaigns.get(row['campaign'])
            if not campaign:
                continue
            donor = users.get(row['donor']) if row['donor'] else None
            amount = Decimal(str(row['amount']))
            fee = (amount * fee_rate).quantize(Decimal('0.01'))
            paid_at = now - timedelta(days=row['days_ago'], hours=2)
            Donation.objects.create(
                campaign=campaign,
                donor=donor,
                amount=amount,
                fee=fee,
                phone=row['phone'],
                provider='wave',
                status=Donation.Status.PAID,
                is_anonymous=row['anon'],
                message=row['msg'],
                payment_reference=make_ref(),
                paid_at=paid_at,
            )
            count += 1
        self.stdout.write(f'  + {count} donations created')

    # ─── Payouts ─────────────────────────────────────────────────────────────

    def _seed_payouts(self, campaigns, users):
        from apps.payments.models import Payout
        import uuid

        def ref():
            return f'PO-{uuid.uuid4().hex[:12].upper()}'

        now = timezone.now()
        fee_rate = Decimal('0.01')

        payouts = [
            dict(
                campaign='help-fatou-get-kidney-surgery',
                requested_by='omar.jallow@example.gm',
                amount=Decimal('50000.00'),
                provider='wave', phone='+220 7100001',
                status=Payout.Status.COMPLETED,
                days_ago=21,
            ),
            dict(
                campaign='help-fatou-get-kidney-surgery',
                requested_by='omar.jallow@example.gm',
                amount=Decimal('30000.00'),
                provider='wave', phone='+220 7100001',
                status=Payout.Status.COMPLETED,
                days_ago=8,
            ),
            dict(
                campaign='gambia-tech-hub-banjul',
                requested_by='ousman@sada.gm',
                amount=Decimal('100000.00'),
                provider='wave', phone='+220 7612345',
                status=Payout.Status.COMPLETED,
                days_ago=15,
            ),
        ]

        count = 0
        for row in payouts:
            campaign = campaigns.get(row['campaign'])
            if not campaign:
                continue
            user = users.get(row['requested_by'])
            amount = row['amount']
            fee = (amount * fee_rate).quantize(Decimal('0.01'))
            net = amount - fee
            proc = now - timedelta(days=row['days_ago'])
            Payout.objects.create(
                campaign=campaign,
                requested_by=user,
                amount=amount, fee=fee, net_amount=net,
                provider=row['provider'], phone=row['phone'],
                reference=ref(),
                status=row['status'],
                processed_at=proc,
            )
            count += 1
        self.stdout.write(f'  + {count} payouts created')

    # ─── Summary ─────────────────────────────────────────────────────────────

    def _print_summary(self, users, cats, campaigns):
        from apps.donations.models import Donation
        from apps.payments.models import Payout
        from apps.campaigns.models import Campaign
        self.stdout.write('\n' + '─' * 50)
        self.stdout.write(self.style.SUCCESS('Seed Summary'))
        self.stdout.write(f'  Users:     {User.objects.count()}')
        self.stdout.write(f'  Categories:{len(cats)}')
        self.stdout.write(f'  Campaigns: {Campaign.objects.count()}')
        self.stdout.write(f'  Donations: {Donation.objects.count()}')
        self.stdout.write(f'  Payouts:   {Payout.objects.count()}')
        self.stdout.write('─' * 50)
        self.stdout.write('\nTest accounts (password: User@1234 for all):')
        self.stdout.write('  admin@sada.gm   — Admin')
        self.stdout.write('  ousman@sada.gm  — Campaign owner (Tech Bootcamp)')
        self.stdout.write('  omar.jallow@example.gm — Campaign owner (Help Fatou)')
        self.stdout.write('  aminata.k@example.gm  — Donor')
        self.stdout.write('  Admin password: Admin@1234')
