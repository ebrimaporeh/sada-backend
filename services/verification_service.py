from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.users.models import User, IdentityVerification


def submit_verification(user: User, id_type: str, id_number: str, id_photo_front, id_photo_back=None) -> IdentityVerification:
    if user.is_verified:
        raise ValidationError('Your identity is already verified.')
    if user.verification_requests.filter(status=IdentityVerification.Status.PENDING).exists():
        raise ValidationError('You already have a pending verification request.')

    verification = IdentityVerification.objects.create(
        user=user,
        id_type=id_type,
        id_number=id_number,
        id_photo_front=id_photo_front,
        id_photo_back=id_photo_back,
    )

    from emails.tasks import send_new_verification_notification_task
    send_new_verification_notification_task.delay(str(verification.id))

    return verification


def get_latest_verification(user: User) -> IdentityVerification | None:
    return user.verification_requests.first()


def get_all_verifications(status: str = None, user_id: str = None) -> 'QuerySet[IdentityVerification]':
    qs = IdentityVerification.objects.select_related('user', 'reviewed_by')
    if status:
        qs = qs.filter(status=status)
    if user_id:
        qs = qs.filter(user_id=user_id)
    return qs


def _get_pending(verification_id: str) -> IdentityVerification:
    try:
        verification = IdentityVerification.objects.select_related('user').get(id=verification_id)
    except IdentityVerification.DoesNotExist:
        raise ValidationError('Verification request not found.')
    if verification.status != IdentityVerification.Status.PENDING:
        raise ValidationError('This request has already been reviewed.')
    return verification


def approve_verification(verification_id: str, admin_user: User) -> IdentityVerification:
    from emails.tasks import send_verification_reviewed_email_task

    with transaction.atomic():
        verification = _get_pending(verification_id)
        verification.status = IdentityVerification.Status.APPROVED
        verification.reviewed_by = admin_user
        verification.reviewed_at = timezone.now()
        verification.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

        verification.user.is_verified = True
        verification.user.save(update_fields=['is_verified'])

    send_verification_reviewed_email_task.delay(str(verification.id))
    return verification


def reject_verification(verification_id: str, admin_user: User, reason: str = '') -> IdentityVerification:
    from emails.tasks import send_verification_reviewed_email_task

    verification = _get_pending(verification_id)
    verification.status = IdentityVerification.Status.REJECTED
    verification.rejection_reason = reason
    verification.reviewed_by = admin_user
    verification.reviewed_at = timezone.now()
    verification.save(update_fields=['status', 'rejection_reason', 'reviewed_by', 'reviewed_at'])

    send_verification_reviewed_email_task.delay(str(verification.id))
    return verification


def revoke_verification(user: User, admin_user: User) -> None:
    """Called when an admin flips a verified user back to unverified (e.g. via
    the admin user editor) — marks their approved submission as rejected so
    verification.status and user.is_verified can never contradict each other,
    and so the user sees why and can resubmit rather than hitting a dead end.
    """
    from emails.tasks import send_verification_reviewed_email_task

    verifications = user.verification_requests.filter(status=IdentityVerification.Status.APPROVED)
    for verification in verifications:
        verification.status = IdentityVerification.Status.REJECTED
        verification.rejection_reason = 'Your verification was revoked by an administrator. Please resubmit your ID for review.'
        verification.reviewed_by = admin_user
        verification.reviewed_at = timezone.now()
        verification.save(update_fields=['status', 'rejection_reason', 'reviewed_by', 'reviewed_at'])
        send_verification_reviewed_email_task.delay(str(verification.id))
