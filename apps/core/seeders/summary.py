def print_summary(stdout, style, users, cats, campaigns):
    from apps.users.models import User, Organization
    from apps.donations.models import Donation
    from apps.payments.models import Payout
    from apps.campaigns.models import Campaign

    stdout.write('\n' + '─' * 50)
    stdout.write(style.SUCCESS('Seed Summary'))
    stdout.write(f'  Users:     {User.objects.count()}')
    stdout.write(f'  Organizations: {Organization.objects.count()}')
    stdout.write(f'  Categories:{len(cats)}')
    stdout.write(f'  Campaigns: {Campaign.objects.count()}')
    stdout.write(f'  Donations: {Donation.objects.count()}')
    stdout.write(f'  Payouts:   {Payout.objects.count()}')
    stdout.write('─' * 50)
    stdout.write('\nTest accounts (password: User@1234 for all):')
    stdout.write('  admin@sada.gm   — Admin')
    stdout.write('  ousman@sada.gm  — Campaign owner (Tech Bootcamp)')
    stdout.write('  omar.jallow@example.gm — Campaign owner (Help Fatou)')
    stdout.write('  aminata.k@example.gm  — Donor')
    stdout.write('  bakau.mosque@example.gm — Organization (religious)')
    stdout.write('  utgsu@example.gm — Organization (student union)')
    stdout.write('  naatip@example.gm — Organization (national agency)')
    stdout.write('  Admin password: Admin@1234')
