import logging
from celery import shared_task

logger = logging.getLogger(__name__)

RETRY_KWARGS = {'bind': True, 'max_retries': 3, 'default_retry_delay': 60}


def _retry_on_failure(task, sent: bool, description: str):
    """EmailService swallows send errors (returns False, logs, never raises) —
    turn a failed send back into an exception so Celery's retry actually fires."""
    if not sent:
        raise task.retry(exc=Exception(f'Email send failed: {description}'))


@shared_task(**RETRY_KWARGS)
def send_welcome_email_task(self, user_id):
    from apps.users.models import User
    from emails.service import email_service
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning('send_welcome_email_task: user %s not found', user_id)
        return
    _retry_on_failure(self, email_service.send_welcome_email(user), f'welcome email to user {user_id}')


@shared_task(**RETRY_KWARGS)
def send_password_reset_email_task(self, user_id, reset_url):
    from apps.users.models import User
    from emails.service import email_service
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning('send_password_reset_email_task: user %s not found', user_id)
        return
    _retry_on_failure(self, email_service.send_password_reset_email(user, reset_url), f'password reset email to user {user_id}')


@shared_task(**RETRY_KWARGS)
def send_password_changed_email_task(self, user_id):
    from apps.users.models import User
    from emails.service import email_service
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning('send_password_changed_email_task: user %s not found', user_id)
        return
    _retry_on_failure(self, email_service.send_password_changed_email(user), f'password changed email to user {user_id}')


@shared_task(**RETRY_KWARGS)
def send_verification_email_task(self, user_id, verification_url):
    from apps.users.models import User
    from emails.service import email_service
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning('send_verification_email_task: user %s not found', user_id)
        return
    _retry_on_failure(self, email_service.send_verification_email(user, verification_url), f'verification email to user {user_id}')


@shared_task(**RETRY_KWARGS)
def send_campaign_status_update_email_task(self, user_id, campaign_id, new_status, reason=''):
    from apps.users.models import User
    from apps.campaigns.models import Campaign
    from emails.service import email_service
    try:
        user = User.objects.get(pk=user_id)
        campaign = Campaign.objects.get(pk=campaign_id)
    except (User.DoesNotExist, Campaign.DoesNotExist):
        logger.warning('send_campaign_status_update_email_task: user %s or campaign %s not found', user_id, campaign_id)
        return
    _retry_on_failure(
        self, email_service.send_campaign_status_update_email(user, campaign, new_status, reason),
        f'campaign status update email to user {user_id}',
    )


@shared_task(**RETRY_KWARGS)
def send_donation_received_email_task(self, donation_id):
    from apps.donations.models import Donation
    from emails.service import email_service
    try:
        donation = Donation.objects.select_related('campaign', 'campaign__owner').get(pk=donation_id)
    except Donation.DoesNotExist:
        logger.warning('send_donation_received_email_task: donation %s not found', donation_id)
        return
    owner = donation.campaign.owner
    if not owner or not owner.notify_donations_received:
        return
    _retry_on_failure(self, email_service.send_donation_received_email(owner, donation), f'donation received email for donation {donation_id}')


@shared_task(**RETRY_KWARGS)
def send_payout_update_email_task(self, payout_id):
    from apps.payments.models import Payout
    from emails.service import email_service
    try:
        payout = Payout.objects.select_related('campaign', 'campaign__owner', 'requested_by').get(pk=payout_id)
    except Payout.DoesNotExist:
        logger.warning('send_payout_update_email_task: payout %s not found', payout_id)
        return
    owner = payout.requested_by or payout.campaign.owner
    _retry_on_failure(self, email_service.send_payout_update_email(owner, payout), f'payout update email for payout {payout_id}')


@shared_task(**RETRY_KWARGS)
def send_verification_reviewed_email_task(self, verification_id):
    from apps.users.models import IdentityVerification
    from emails.service import email_service
    try:
        verification = IdentityVerification.objects.select_related('user').get(pk=verification_id)
    except IdentityVerification.DoesNotExist:
        logger.warning('send_verification_reviewed_email_task: verification %s not found', verification_id)
        return
    _retry_on_failure(
        self, email_service.send_verification_reviewed_email(verification.user, verification),
        f'verification reviewed email for verification {verification_id}',
    )
