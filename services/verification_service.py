from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.users.models import User, IdentityVerification, OrganizationVerification


def submit_verification(user: User, id_type: str, id_number: str, id_photo_front, id_photo_back=None) -> IdentityVerification:
    if user.is_verified:
        raise ValidationError('Your identity is already verified.')
    if user.verification_requests.filter(status=IdentityVerification.Status.PENDING).exists():
        raise ValidationError('You already have a pending verification request.')

    from services.image_compression import process_image
    verification = IdentityVerification.objects.create(
        user=user,
        id_type=id_type,
        id_number=id_number,
        id_photo_front=process_image(id_photo_front, profile='document'),
        id_photo_back=process_image(id_photo_back, profile='document') if id_photo_back else None,
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
    from emails.tasks import send_verification_reviewed_email_task, send_organization_verification_reviewed_email_task

    verifications = user.verification_requests.filter(status=IdentityVerification.Status.APPROVED)
    for verification in verifications:
        verification.status = IdentityVerification.Status.REJECTED
        verification.rejection_reason = 'Your verification was revoked by an administrator. Please resubmit your ID for review.'
        verification.reviewed_by = admin_user
        verification.reviewed_at = timezone.now()
        verification.save(update_fields=['status', 'rejection_reason', 'reviewed_by', 'reviewed_at'])
        send_verification_reviewed_email_task.delay(str(verification.id))

    org_verifications = user.organization_verification_requests.filter(status=OrganizationVerification.Status.APPROVED)
    for verification in org_verifications:
        verification.status = OrganizationVerification.Status.REJECTED
        verification.rejection_reason = 'Your verification was revoked by an administrator. Please resubmit your documents for review.'
        verification.reviewed_by = admin_user
        verification.reviewed_at = timezone.now()
        verification.save(update_fields=['status', 'rejection_reason', 'reviewed_by', 'reviewed_at'])
        send_organization_verification_reviewed_email_task.delay(str(verification.id))


# ─── Organization verification ──────────────────────────────────────────────
# Mirrors the individual-verification functions above exactly (same
# is_verified-flips-only-on-approve invariant), just against
# OrganizationVerification/organization_verification_requests instead.

def submit_organization_verification(
    user: User, contact_id_type: str, contact_id_number: str,
    contact_id_photo_front, registration_document, organization_photo, contact_id_photo_back=None,
) -> OrganizationVerification:
    if not user.is_organization:
        raise ValidationError('Only organization accounts can submit organization verification.')
    if user.is_verified:
        raise ValidationError('Your organization is already verified.')
    if user.organization_verification_requests.filter(status=OrganizationVerification.Status.PENDING).exists():
        raise ValidationError('You already have a pending verification request.')

    from services.image_compression import process_image
    verification = OrganizationVerification.objects.create(
        user=user,
        contact_id_type=contact_id_type,
        contact_id_number=contact_id_number,
        contact_id_photo_front=process_image(contact_id_photo_front, profile='document'),
        contact_id_photo_back=process_image(contact_id_photo_back, profile='document') if contact_id_photo_back else None,
        registration_document=process_image(registration_document, profile='document'),
        organization_photo=process_image(organization_photo, profile='document'),
    )

    from emails.tasks import send_new_organization_verification_notification_task
    send_new_organization_verification_notification_task.delay(str(verification.id))

    return verification


def get_latest_organization_verification(user: User) -> OrganizationVerification | None:
    return user.organization_verification_requests.first()


def get_all_organization_verifications(status: str = None, user_id: str = None) -> 'QuerySet[OrganizationVerification]':
    qs = OrganizationVerification.objects.select_related('user', 'user__organization', 'reviewed_by')
    if status:
        qs = qs.filter(status=status)
    if user_id:
        qs = qs.filter(user_id=user_id)
    return qs


def _get_pending_org(verification_id: str) -> OrganizationVerification:
    try:
        verification = OrganizationVerification.objects.select_related('user', 'user__organization').get(id=verification_id)
    except OrganizationVerification.DoesNotExist:
        raise ValidationError('Verification request not found.')
    if verification.status != OrganizationVerification.Status.PENDING:
        raise ValidationError('This request has already been reviewed.')
    return verification


def approve_organization_verification(verification_id: str, admin_user: User) -> OrganizationVerification:
    from emails.tasks import send_organization_verification_reviewed_email_task

    with transaction.atomic():
        verification = _get_pending_org(verification_id)
        verification.status = OrganizationVerification.Status.APPROVED
        verification.reviewed_by = admin_user
        verification.reviewed_at = timezone.now()
        verification.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

        verification.user.is_verified = True
        verification.user.save(update_fields=['is_verified'])

        # The submitted org photo becomes the org's public logo on approval.
        org = verification.user.organization
        org.logo = verification.organization_photo
        org.save(update_fields=['logo'])

    send_organization_verification_reviewed_email_task.delay(str(verification.id))
    return verification


def reject_organization_verification(verification_id: str, admin_user: User, reason: str = '') -> OrganizationVerification:
    from emails.tasks import send_organization_verification_reviewed_email_task

    verification = _get_pending_org(verification_id)
    verification.status = OrganizationVerification.Status.REJECTED
    verification.rejection_reason = reason
    verification.reviewed_by = admin_user
    verification.reviewed_at = timezone.now()
    verification.save(update_fields=['status', 'rejection_reason', 'reviewed_by', 'reviewed_at'])

    send_organization_verification_reviewed_email_task.delay(str(verification.id))
    return verification
