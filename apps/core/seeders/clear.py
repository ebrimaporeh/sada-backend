from apps.users.models import User


def clear_all(stdout):
    """Deletes all seeded data, in FK-safe order, keeping any superuser
    created outside the seeder (e.g. via createsuperuser)."""
    from apps.payments.models import Payout, Payment
    from apps.donations.models import Donation
    from apps.campaigns.models import Campaign, Category, CampaignUpdate, CampaignImage
    from apps.notifications.models import Notification

    stdout.write('Clearing existing data...')
    Notification.objects.all().delete()
    Payout.objects.all().delete()
    Payment.objects.all().delete()
    Donation.objects.all().delete()
    CampaignUpdate.objects.all().delete()
    CampaignImage.objects.all().delete()
    Campaign.objects.all().delete()
    Category.objects.all().delete()
    User.objects.filter(is_superuser=False).delete()
    stdout.write('  Done.')
