def _build_updates_data(campaigns, users):
    return [
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


def seed_updates(stdout, campaigns, users):
    from apps.campaigns.models import CampaignUpdate

    count = 0
    for data in _build_updates_data(campaigns, users):
        if data['campaign'] and not CampaignUpdate.objects.filter(
            campaign=data['campaign'], title=data['title']
        ).exists():
            CampaignUpdate.objects.create(**data)
            count += 1
    stdout.write(f'  + {count} updates created')
