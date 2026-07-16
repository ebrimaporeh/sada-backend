from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone


def _build_campaigns_data(users, cats):
    """Campaign fixtures reference live User/Category objects and relative
    dates, so this builds the list at call time rather than as a module
    constant."""
    from apps.campaigns.models import Campaign

    today = date.today()
    U = users
    active = Campaign.Status.ACTIVE

    return [
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
            deadline=today + timedelta(days=40), status=active,
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
            deadline=today + timedelta(days=88), status=active,
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
            deadline=today + timedelta(days=25), status=active,
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
            deadline=today + timedelta(days=76), status=active,
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
            deadline=today + timedelta(days=147), status=active,
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
            deadline=today + timedelta(days=26), status=active,
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
            deadline=today + timedelta(days=71), status=active,
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
            deadline=today + timedelta(days=55), status=active,
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
            deadline=today + timedelta(days=102), status=active,
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
            deadline=today + timedelta(days=178), status=active,
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
            deadline=today + timedelta(days=57), status=active,
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
            deadline=today + timedelta(days=118), status=active,
            region='banjul', beneficiary='100 Young Gambians', beneficiary_relationship='Students',
            is_urgent=False, is_featured=False,
            approved_at=timezone.now() - timedelta(days=56),
        ),
        dict(
            slug='bakau-mosque-water-system',
            owner=U.get('bakau.mosque@example.gm'),
            category=cats.get('religious'),
            title='New Wudu (Ablution) Water System for Bakau Mosque',
            short_description="Bakau Central Mosque's water system is failing. Help us install a reliable new system for daily prayers.",
            story="""Bakau Central Mosque serves hundreds of worshippers daily, but our ablution water system — installed over 20 years ago — is now failing regularly, leaving worshippers without water for wudu ahead of prayers.

This campaign will fund a full replacement: new piping, storage tanks, and taps across the mosque's ablution area, sized for daily demand during Friday prayers and Ramadan.

All funds are managed transparently by the mosque committee, with receipts published to the community.""",
            goal=Decimal('180000.00'), raised=Decimal('64000.00'), donors_count=97,
            deadline=today + timedelta(days=90), status=active,
            region='kanifing', beneficiary='Bakau Central Mosque', beneficiary_relationship='Religious Institution',
            is_urgent=False, is_featured=False,
            approved_at=timezone.now() - timedelta(days=40),
        ),
        dict(
            slug='utg-su-graduation-fund',
            owner=U.get('utgsu@example.gm'),
            category=cats.get('education'),
            title="UTG Students' Union Graduation Support Fund",
            short_description='Help cover graduation fees and regalia for final-year UTG students who cannot afford them.',
            story="""Every year, a number of final-year students at the University of The Gambia are unable to complete their graduation requirements — regalia hire, graduation fees, and transcript costs — due to financial hardship.

The UTG Students' Union is raising funds to support these students directly, so financial hardship never stands between a student and their graduation ceremony.

Funds are disbursed by the Students' Union executive committee based on verified need, with full transparency to the student body.""",
            goal=Decimal('120000.00'), raised=Decimal('38500.00'), donors_count=64,
            deadline=today + timedelta(days=75), status=active,
            region='brikama', beneficiary='UTG Final-Year Students', beneficiary_relationship='Students',
            is_urgent=False, is_featured=False,
            approved_at=timezone.now() - timedelta(days=30),
        ),
    ]


def seed_campaigns(stdout, users, cats) -> dict:
    """Creates campaign fixtures, returns {slug: Campaign} for downstream seeders."""
    from apps.campaigns.models import Campaign

    created = {}
    for data in _build_campaigns_data(users, cats):
        slug = data['slug']
        if not Campaign.objects.filter(slug=slug).exists():
            Campaign.objects.create(**data)
            stdout.write(f'  + {data["title"][:55]}')
        else:
            stdout.write(f'  ~ {data["title"][:55]} (exists)')
        created[slug] = Campaign.objects.get(slug=slug)
    return created
