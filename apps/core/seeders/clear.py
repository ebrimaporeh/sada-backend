from apps.users.models import User


def clear_all(stdout):
    """Deletes all seeded data, in FK-safe order, keeping any superuser
    created outside the seeder (e.g. via createsuperuser)."""
    from apps.payments.models import Payout, Payment
    from apps.donations.models import Donation
    from apps.campaigns.models import Campaign, Category, CampaignUpdate, CampaignImage
    from apps.notifications.models import Notification
    from apps.users.models import Organization, OrganizationVerification, OrganizationChangeRequest
    from apps.organizations.models import OrganizationRole, OrganizationMembership, OrganizationInvitation

    stdout.write('Clearing existing data...')
    Notification.objects.all().delete()
    Payout.objects.all().delete()
    Payment.objects.all().delete()
    Donation.objects.all().delete()
    CampaignUpdate.objects.all().delete()
    CampaignImage.objects.all().delete()
    Campaign.objects.all().delete()
    Category.objects.all().delete()
    # Organization.created_by is SET_NULL and OrganizationRole/Invitation/
    # Verification/ChangeRequest all CASCADE from Organization, not from
    # User -- none of these get cleaned up by the User delete below, so a
    # re-seed would otherwise find each org still existing (by name, via
    # get_or_create) but with its membership already gone (that one *does*
    # cascade from User), and skip recreating the Owner role/membership
    # since the org "already existed". Clear them explicitly, children
    # before parents. OrganizationType is deliberately not cleared here --
    # it's migration-seeded and reused via get_or_create, not per-seed-run data.
    OrganizationInvitation.objects.all().delete()
    OrganizationVerification.objects.all().delete()
    OrganizationChangeRequest.objects.all().delete()
    OrganizationMembership.objects.all().delete()
    OrganizationRole.objects.all().delete()
    Organization.objects.all().delete()
    User.objects.filter(is_superuser=False).delete()
    stdout.write('  Done.')
