import uuid
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone

DONATIONS_DATA = [
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

FEE_RATE = Decimal('0.015')


def _make_reference():
    return f'GF-{uuid.uuid4().hex[:12].upper()}'


def seed_donations(stdout, campaigns, users):
    from apps.donations.models import Donation

    now = timezone.now()
    count = 0
    for row in DONATIONS_DATA:
        campaign = campaigns.get(row['campaign'])
        if not campaign:
            continue
        donor = users.get(row['donor']) if row['donor'] else None
        amount = Decimal(str(row['amount']))
        fee = (amount * FEE_RATE).quantize(Decimal('0.01'))
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
            payment_reference=_make_reference(),
            paid_at=paid_at,
        )
        count += 1
    stdout.write(f'  + {count} donations created')
