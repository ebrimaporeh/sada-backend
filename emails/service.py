from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class EmailService:
    def _send(self, to: str, subject: str, template: str, context: dict) -> bool:
        try:
            context = {'site_name': settings.SITE_NAME, 'frontend_url': settings.FRONTEND_URL, **context}
            html_content = render_to_string(template, context)
            msg = EmailMultiAlternatives(
                subject=subject,
                body=strip_tags(html_content),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[to],
            )
            msg.attach_alternative(html_content, 'text/html')
            msg.send()
            return True
        except Exception as e:
            logger.error(f'Failed to send email to {to}: {e}')
            return False

    def send_welcome_email(self, user) -> bool:
        return self._send(
            to=user.email,
            subject=f'Welcome to {settings.SITE_NAME}!',
            template='emails/welcome.html',
            context={'user': user},
        )

    def send_password_reset_email(self, user, reset_url: str) -> bool:
        return self._send(
            to=user.email,
            subject=f'Reset your {settings.SITE_NAME} password',
            template='emails/password_reset.html',
            context={'user': user, 'reset_url': reset_url},
        )

    def send_password_changed_email(self, user) -> bool:
        return self._send(
            to=user.email,
            subject=f'Your {settings.SITE_NAME} password was changed',
            template='emails/password_changed.html',
            context={'user': user},
        )

    def send_verification_email(self, user, verification_url: str) -> bool:
        return self._send(
            to=user.email,
            subject=f'Verify your {settings.SITE_NAME} email',
            template='emails/verification.html',
            context={'user': user, 'verification_url': verification_url},
        )

    def send_plain_email(self, to: str, subject: str, message: str) -> bool:
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to],
            )
            return True
        except Exception as e:
            logger.error(f'Failed to send email to {to}: {e}')
            return False

    def send_campaign_status_update_email(self, user, campaign, new_status: str, reason: str = '') -> bool:
        return self._send(
            to=user.email,
            subject=f'Campaign Status Update: {campaign.title}',
            template='emails/campaign_status_update.html',
            context={
                'campaign_owner_name': user.full_name or user.email,
                'campaign_title': campaign.title,
                'campaign_slug': campaign.slug,
                'new_status': new_status,
                'reason': reason,
            },
        )

    def send_donation_received_email(self, owner, donation) -> bool:
        return self._send(
            to=owner.email,
            subject=f'New donation to "{donation.campaign.title}"!',
            template='emails/donation_received.html',
            context={
                'owner_name': owner.full_name or owner.email,
                'donor_name': donation.donor_display,
                'amount': donation.amount,
                'message': donation.message,
                'campaign_title': donation.campaign.title,
                'campaign_slug': donation.campaign.slug,
                'campaign_raised': donation.campaign.raised,
                'campaign_goal': donation.campaign.goal,
                'campaign_progress_percent': donation.campaign.progress_percent,
            },
        )

    def send_verification_reviewed_email(self, user, verification) -> bool:
        approved = verification.status == 'approved'
        return self._send(
            to=user.email,
            subject=f'Your {settings.SITE_NAME} identity verification was {"approved" if approved else "rejected"}',
            template='emails/verification_reviewed.html',
            context={
                'user': user,
                'approved': approved,
                'rejection_reason': verification.rejection_reason,
            },
        )

    def send_new_report_notification_email(self, moderator, report) -> bool:
        return self._send(
            to=moderator.email,
            subject=f'New report: "{report.campaign.title}"',
            template='emails/new_report_notification.html',
            context={
                'moderator_name': moderator.full_name or moderator.email,
                'campaign_title': report.campaign.title,
                'reason_label': report.get_reason_display(),
                'reporter_name': report.reported_by.full_name if report.reported_by else (report.reporter_name or 'Anonymous'),
                'description': report.description,
            },
        )

    def send_new_verification_notification_email(self, moderator, verification) -> bool:
        return self._send(
            to=moderator.email,
            subject=f'New identity verification from {verification.user.full_name or verification.user.email}',
            template='emails/new_verification_notification.html',
            context={
                'moderator_name': moderator.full_name or moderator.email,
                'submitter_name': verification.user.full_name or verification.user.email,
                'submitter_email': verification.user.email,
                'id_type_label': verification.get_id_type_display(),
            },
        )

    def send_organization_verification_reviewed_email(self, user, verification) -> bool:
        approved = verification.status == 'approved'
        return self._send(
            to=user.email,
            subject=f'Your {settings.SITE_NAME} organization verification was {"approved" if approved else "rejected"}',
            template='emails/organization_verification_reviewed.html',
            context={
                'user': user,
                'approved': approved,
                'rejection_reason': verification.rejection_reason,
            },
        )

    def send_new_organization_verification_notification_email(self, moderator, verification) -> bool:
        return self._send(
            to=moderator.email,
            subject=f'New organization verification from {verification.user.full_name or verification.user.email}',
            template='emails/new_organization_verification_notification.html',
            context={
                'moderator_name': moderator.full_name or moderator.email,
                'submitter_name': verification.user.full_name or verification.user.email,
                'submitter_email': verification.user.email,
                'org_type_label': verification.user.organization.get_organization_type_display(),
            },
        )

    def send_payout_update_email(self, owner, payout) -> bool:
        subject_by_status = {
            'completed': f'Your withdrawal of D{payout.net_amount} has arrived',
            'processing': f'Your withdrawal of D{payout.net_amount} is on its way',
            'pending': f'Your withdrawal of D{payout.net_amount} is on hold',
            'failed': f'Your withdrawal of D{payout.net_amount} could not be completed',
        }
        return self._send(
            to=owner.email,
            subject=subject_by_status.get(payout.status, f'Withdrawal update: {payout.campaign.title}'),
            template='emails/payout_update.html',
            context={
                'owner_name': owner.full_name or owner.email,
                'campaign_title': payout.campaign.title,
                'campaign_slug': payout.campaign.slug,
                'amount': payout.amount,
                'fee': payout.fee,
                'net_amount': payout.net_amount,
                'provider': payout.provider,
                'phone': payout.phone,
                'status': payout.status,
                'reference': payout.reference,
            },
        )


email_service = EmailService()
