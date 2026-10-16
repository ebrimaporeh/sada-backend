"""Celery tasks wrapping sms.service.SmsService, same shape as emails/tasks.py:
take primitive IDs (Celery args must be JSON-serializable), re-fetch inside
the task.

Deliberately NOT using emails/tasks.py's _retry_on_failure/max_retries
pattern. Email failures are usually transient (a network blip hitting
Resend); most SMS failures here aren't - SmsService._send() already returns
False, without ever reaching the provider, whenever NotificationSettings.sms_enabled
is off (the default) or the recipient has no usable phone number, and
Jokoor's own failure modes (invalid number, insufficient credit, bad key)
won't resolve by retrying the same request 3 times either. Retrying those
would just mean every queued SMS task retries uselessly, with backoff, for
as long as SMS stays in its default off state. A real provider outage is
logged (see SmsService._send) and left for a human, not auto-retried - SMS
is a best-effort channel layered on top of email + in-app, which remain the
source of truth regardless of whether the SMS send succeeded.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def send_password_changed_sms_task(user_id):
    from apps.users.models import User
    from .service import sms_service
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning('send_password_changed_sms_task: user %s not found', user_id)
        return
    sms_service.send_password_changed_sms(user)


@shared_task
def send_verification_reviewed_sms_task(verification_id):
    from apps.users.models import IdentityVerification
    from .service import sms_service
    try:
        verification = IdentityVerification.objects.select_related('user').get(pk=verification_id)
    except IdentityVerification.DoesNotExist:
        logger.warning('send_verification_reviewed_sms_task: verification %s not found', verification_id)
        return
    sms_service.send_verification_reviewed_sms(verification.user, verification)


@shared_task
def send_campaign_approved_sms_task(campaign_id):
    from apps.campaigns.models import Campaign
    from .service import sms_service
    try:
        campaign = Campaign.objects.select_related('owner').get(pk=campaign_id)
    except Campaign.DoesNotExist:
        logger.warning('send_campaign_approved_sms_task: campaign %s not found', campaign_id)
        return
    sms_service.send_campaign_approved_sms(campaign.owner, campaign)


@shared_task
def send_campaign_rejected_sms_task(campaign_id, reason=''):
    from apps.campaigns.models import Campaign
    from .service import sms_service
    try:
        campaign = Campaign.objects.select_related('owner').get(pk=campaign_id)
    except Campaign.DoesNotExist:
        logger.warning('send_campaign_rejected_sms_task: campaign %s not found', campaign_id)
        return
    sms_service.send_campaign_rejected_sms(campaign.owner, campaign, reason)


@shared_task
def send_campaign_suspended_sms_task(campaign_id, reason=''):
    from apps.campaigns.models import Campaign
    from .service import sms_service
    try:
        campaign = Campaign.objects.select_related('owner').get(pk=campaign_id)
    except Campaign.DoesNotExist:
        logger.warning('send_campaign_suspended_sms_task: campaign %s not found', campaign_id)
        return
    sms_service.send_campaign_suspended_sms(campaign.owner, campaign, reason)


@shared_task
def send_goal_reached_sms_task(campaign_id):
    from apps.campaigns.models import Campaign
    from .service import sms_service
    try:
        campaign = Campaign.objects.select_related('owner').get(pk=campaign_id)
    except Campaign.DoesNotExist:
        logger.warning('send_goal_reached_sms_task: campaign %s not found', campaign_id)
        return
    sms_service.send_goal_reached_sms(campaign.owner, campaign)


@shared_task
def send_donation_received_sms_task(donation_id):
    from apps.donations.models import Donation
    from services.donation_service import _donation_recipients
    from .service import sms_service
    try:
        donation = Donation.objects.select_related('campaign', 'campaign__owner', 'organization').get(pk=donation_id)
    except Donation.DoesNotExist:
        logger.warning('send_donation_received_sms_task: donation %s not found', donation_id)
        return
    # Same recipient set as the email task (donation_service._donation_recipients) -
    # one campaign owner, or every org member with manage_organization for a
    # direct organization donation. Unlike the email task, this doesn't
    # gate on notify_donations_received -- that field predates SMS and
    # reads as an email preference in its help text; reusing it here would
    # silently start texting anyone who'd only ever opted into email. Gated
    # instead by the single NotificationSettings.sms_enabled switch, same as
    # every other SMS trigger, until there's a real per-channel preference.
    for recipient in _donation_recipients(donation):
        if recipient:
            sms_service.send_donation_received_sms(recipient, donation)


@shared_task
def send_donation_refunded_sms_task(donation_id):
    from apps.donations.models import Donation
    from .service import sms_service
    try:
        donation = Donation.objects.select_related('campaign', 'organization', 'donor').get(pk=donation_id)
    except Donation.DoesNotExist:
        logger.warning('send_donation_refunded_sms_task: donation %s not found', donation_id)
        return
    if not donation.donor:
        return
    sms_service.send_donation_refunded_sms(donation.donor, donation)


@shared_task
def send_payout_update_sms_task(payout_id):
    from apps.payments.models import Payout
    from .service import sms_service
    try:
        payout = Payout.objects.select_related('campaign', 'campaign__owner', 'requested_by').get(pk=payout_id)
    except Payout.DoesNotExist:
        logger.warning('send_payout_update_sms_task: payout %s not found', payout_id)
        return
    owner = payout.requested_by or payout.campaign.owner
    sms_service.send_payout_update_sms(owner, payout)
