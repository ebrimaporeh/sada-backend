"""SmsService - the SMS equivalent of emails/service.py's EmailService.

One method per notification-worthy event, each building a short plain-text
message and going through _send(), the single choke point that:
  1. checks apps.common.models.NotificationSettings.sms_enabled (the admin
     toggle, off by default - see that model's docstring),
  2. normalizes the recipient's stored phone to E.164 and skips silently if
     there isn't a usable one,
  3. hands off to sms.registry.get_provider() - never a concrete provider
     class directly, so swapping SMS_PROVIDER in settings is enough to
     switch providers; nothing below this file changes.

Call sites never check NotificationSettings or the phone themselves (same
reasoning as EmailService: one place to get the gate right, not N places to
forget it) - they just call sms_service.send_whatever_sms(...) the same way
they already call email_service.send_whatever_email(...), from
sms/tasks.py's Celery tasks.
"""
import logging
from .registry import get_provider

logger = logging.getLogger(__name__)


class SmsService:
    def _enabled(self) -> bool:
        from apps.common.models import NotificationSettings
        return NotificationSettings.get_solo().sms_enabled

    def _send(self, to: str, message: str) -> bool:
        from utils.helpers import to_e164_gambia

        if not self._enabled():
            return False
        phone = to_e164_gambia(to or '')
        if not phone:
            logger.info('SMS skipped - no usable phone number (raw=%r).', to)
            return False
        result = get_provider().send(phone, message)
        if not result.ok:
            logger.error('Failed to send SMS to %s: %s', phone, result.error)
            return False
        return True

    # ─── Account / security ──────────────────────────────────────────────

    def send_password_changed_sms(self, user) -> bool:
        return self._send(
            user.phone,
            f'Your {self._site_name()} password was just changed. If this wasn\'t you, contact support immediately.',
        )

    def send_verification_reviewed_sms(self, user, verification) -> bool:
        approved = verification.status == 'approved'
        if approved:
            message = f'Your {self._site_name()} identity verification was approved.'
        else:
            reason = f' Reason: {verification.rejection_reason}' if verification.rejection_reason else ''
            message = f'Your {self._site_name()} identity verification was rejected.{reason}'
        return self._send(user.phone, message)

    # ─── Campaigns ────────────────────────────────────────────────────────

    def send_campaign_approved_sms(self, owner, campaign) -> bool:
        return self._send(
            owner.phone,
            f'Good news! Your campaign "{campaign.title}" has been approved and is now live on {self._site_name()}.',
        )

    def send_campaign_rejected_sms(self, owner, campaign, reason='') -> bool:
        suffix = f' Reason: {reason}' if reason else ''
        return self._send(owner.phone, f'Your campaign "{campaign.title}" was not approved.{suffix}')

    def send_campaign_suspended_sms(self, owner, campaign, reason='') -> bool:
        suffix = f' Reason: {reason}' if reason else ''
        return self._send(owner.phone, f'Your campaign "{campaign.title}" has been suspended.{suffix}')

    def send_goal_reached_sms(self, owner, campaign) -> bool:
        return self._send(owner.phone, f'Your campaign "{campaign.title}" just reached its goal!')

    # ─── Donations ────────────────────────────────────────────────────────

    def send_donation_received_sms(self, owner, donation) -> bool:
        return self._send(
            owner.phone,
            f'{donation.donor_display} just donated D{donation.amount} to "{donation.destination_title}".',
        )

    def send_donation_refunded_sms(self, donor, donation) -> bool:
        return self._send(
            donor.phone,
            f'Your donation of D{donation.amount} to "{donation.destination_title}" was refunded.',
        )

    # ─── Payouts ──────────────────────────────────────────────────────────

    def send_payout_update_sms(self, owner, payout) -> bool:
        message_by_status = {
            'completed': f'Your withdrawal of D{payout.net_amount} has arrived.',
            'processing': f'Your withdrawal of D{payout.net_amount} is on its way.',
            'pending': f'Your withdrawal of D{payout.net_amount} is on hold.',
            'failed': f'Your withdrawal of D{payout.net_amount} could not be completed. Check your {self._site_name()} dashboard for details.',
        }
        message = message_by_status.get(payout.status, f'Withdrawal update for "{payout.campaign.title}": {payout.status}.')
        return self._send(owner.phone, message)

    def _site_name(self) -> str:
        from apps.common.models import SiteSettings
        return SiteSettings.get_solo().site_name


sms_service = SmsService()
