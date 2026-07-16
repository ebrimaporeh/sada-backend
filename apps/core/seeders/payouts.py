import uuid
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone


def _build_payouts_data():
    from apps.payments.models import Payout

    return [
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


FEE_RATE = Decimal('0.01')


def _make_reference():
    return f'PO-{uuid.uuid4().hex[:12].upper()}'


def seed_payouts(stdout, campaigns, users):
    from apps.payments.models import Payout

    now = timezone.now()
    count = 0
    for row in _build_payouts_data():
        campaign = campaigns.get(row['campaign'])
        if not campaign:
            continue
        user = users.get(row['requested_by'])
        amount = row['amount']
        fee = (amount * FEE_RATE).quantize(Decimal('0.01'))
        net = amount - fee
        processed_at = now - timedelta(days=row['days_ago'])
        Payout.objects.create(
            campaign=campaign,
            requested_by=user,
            amount=amount, fee=fee, net_amount=net,
            provider=row['provider'], phone=row['phone'],
            reference=_make_reference(),
            status=row['status'],
            processed_at=processed_at,
        )
        count += 1
    stdout.write(f'  + {count} payouts created')
