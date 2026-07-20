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
def send_password_reset_email_task(self, user_id, reset_url, to_email=None):
    from apps.users.models import User
    from emails.service import email_service
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning('send_password_reset_email_task: user %s not found', user_id)
        return
    _retry_on_failure(
        self, email_service.send_password_reset_email(user, reset_url, to_email),
        f'password reset email to user {user_id}',
    )


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
def send_donation_refunded_email_task(self, donation_id):
    from apps.donations.models import Donation
    from emails.service import email_service
    try:
        donation = Donation.objects.select_related('campaign', 'donor').get(pk=donation_id)
    except Donation.DoesNotExist:
        logger.warning('send_donation_refunded_email_task: donation %s not found', donation_id)
        return
    if not donation.donor:
        return
    _retry_on_failure(
        self, email_service.send_donation_refunded_email(donation.donor, donation),
        f'donation refunded email for donation {donation_id}',
    )


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


def _get_moderation_staff():
    """Moderators and admins — everyone with report/verification review
    access (see permissions/roles.py). Broadcast recipients, not a single
    user, so these tasks don't use the retry-the-whole-task pattern above:
    one bad address shouldn't cause every other moderator to get a duplicate
    email on retry.
    """
    from apps.users.models import User
    return User.objects.filter(role__in=[User.Role.MODERATOR, User.Role.ADMIN], is_active=True)


@shared_task(bind=True)
def send_new_report_notification_task(self, report_id):
    from apps.campaigns.models import CampaignReport
    from emails.service import email_service
    try:
        report = CampaignReport.objects.select_related('campaign', 'reported_by').get(pk=report_id)
    except CampaignReport.DoesNotExist:
        logger.warning('send_new_report_notification_task: report %s not found', report_id)
        return
    for moderator in _get_moderation_staff():
        if not email_service.send_new_report_notification_email(moderator, report):
            logger.error('Failed to notify %s about report %s', moderator.email, report_id)


@shared_task(bind=True)
def send_new_verification_notification_task(self, verification_id):
    from apps.users.models import IdentityVerification
    from emails.service import email_service
    try:
        verification = IdentityVerification.objects.select_related('user').get(pk=verification_id)
    except IdentityVerification.DoesNotExist:
        logger.warning('send_new_verification_notification_task: verification %s not found', verification_id)
        return
    for moderator in _get_moderation_staff():
        if not email_service.send_new_verification_notification_email(moderator, verification):
            logger.error('Failed to notify %s about verification %s', moderator.email, verification_id)


@shared_task(**RETRY_KWARGS)
def send_organization_verification_reviewed_email_task(self, verification_id):
    from apps.users.models import OrganizationVerification
    from emails.service import email_service
    try:
        verification = OrganizationVerification.objects.select_related('user').get(pk=verification_id)
    except OrganizationVerification.DoesNotExist:
        logger.warning('send_organization_verification_reviewed_email_task: verification %s not found', verification_id)
        return
    _retry_on_failure(
        self, email_service.send_organization_verification_reviewed_email(verification.user, verification),
        f'organization verification reviewed email for verification {verification_id}',
    )


@shared_task(bind=True)
def send_new_organization_verification_notification_task(self, verification_id):
    from apps.users.models import OrganizationVerification
    from emails.service import email_service
    try:
        verification = OrganizationVerification.objects.select_related('user', 'user__organization').get(pk=verification_id)
    except OrganizationVerification.DoesNotExist:
        logger.warning('send_new_organization_verification_notification_task: verification %s not found', verification_id)
        return
    for moderator in _get_moderation_staff():
        if not email_service.send_new_organization_verification_notification_email(moderator, verification):
            logger.error('Failed to notify %s about organization verification %s', moderator.email, verification_id)


@shared_task(**RETRY_KWARGS)
def send_organization_change_request_reviewed_email_task(self, request_id):
    from apps.users.models import OrganizationChangeRequest
    from emails.service import email_service
    try:
        change_request = OrganizationChangeRequest.objects.select_related('user').get(pk=request_id)
    except OrganizationChangeRequest.DoesNotExist:
        logger.warning('send_organization_change_request_reviewed_email_task: request %s not found', request_id)
        return
    _retry_on_failure(
        self, email_service.send_organization_change_request_reviewed_email(change_request.user, change_request),
        f'organization change request reviewed email for request {request_id}',
    )


@shared_task(bind=True)
def send_new_organization_change_request_notification_task(self, request_id):
    from apps.users.models import OrganizationChangeRequest
    from emails.service import email_service
    try:
        change_request = OrganizationChangeRequest.objects.select_related('user', 'user__organization').get(pk=request_id)
    except OrganizationChangeRequest.DoesNotExist:
        logger.warning('send_new_organization_change_request_notification_task: request %s not found', request_id)
        return
    for moderator in _get_moderation_staff():
        if not email_service.send_new_organization_change_request_notification_email(moderator, change_request):
            logger.error('Failed to notify %s about organization change request %s', moderator.email, request_id)
