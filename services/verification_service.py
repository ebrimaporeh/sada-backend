from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.users.models import User, IdentityVerification


def submit_verification(user: User, id_type: str, id_number: str, id_photo_front, id_photo_back=None) -> IdentityVerification:
    if user.is_verified:
        raise ValidationError('Your identity is already verified.')
    if user.verification_requests.filter(status=IdentityVerification.Status.PENDING).exists():
        raise ValidationError('You already have a pending verification request.')

    return IdentityVerification.objects.create(
        user=user,
        id_type=id_type,
        id_number=id_number,
        id_photo_front=id_photo_front,
        id_photo_back=id_photo_back,
    )


def get_latest_verification(user: User) -> IdentityVerification | None:
    return user.verification_requests.first()


def get_all_verifications(status: str = None) -> 'QuerySet[IdentityVerification]':
    qs = IdentityVerification.objects.select_related('user', 'reviewed_by')
    if status:
        qs = qs.filter(status=status)
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
