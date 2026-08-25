from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.users.models import User, OrganizationChangeRequest

# phone lives on User itself; the other three live on the related Organization
# profile — this map is how approve_change_request() knows where to write.
USER_FIELDS = {OrganizationChangeRequest.Field.PHONE}

# Recovery emails skip admin review entirely -- the proposed address proving
# it controls its own inbox (by clicking the confirmation link sent there)
# is the approval, not a staff member eyeballing a text field. Phone numbers
# still go through the original admin-approval path below; only these two
# fields use the token-based self-service one.
EMAIL_FIELDS = {OrganizationChangeRequest.Field.RECOVERY_EMAIL_1, OrganizationChangeRequest.Field.RECOVERY_EMAIL_2}

RECOVERY_EMAIL_CONFIRM_SALT = 'organization-recovery-email-confirm'
RECOVERY_EMAIL_CONFIRM_MAX_AGE = 60 * 60 * 24 * 7  # 7 days -- longer than the 24h email-verification link since this inbox may not be checked as often.


def generate_recovery_email_confirm_url(change_request: OrganizationChangeRequest) -> str:
    token = signing.dumps(str(change_request.id), salt=RECOVERY_EMAIL_CONFIRM_SALT)
    return f'{settings.FRONTEND_URL}/confirm-recovery-email?token={token}'


def _current_value(user: User, field_name: str) -> str:
    if field_name in USER_FIELDS:
        return user.phone or ''
    return getattr(user.organization, field_name, '') or ''


def submit_change_request(user: User, field_name: str, proposed_value: str) -> OrganizationChangeRequest:
    if not user.is_organization:
        raise ValidationError('Only organization accounts can request this change.')

    current = _current_value(user, field_name)
    if proposed_value == current:
        raise ValidationError('That is already the current value.')

    if user.organization_change_requests.filter(
        field_name=field_name, status=OrganizationChangeRequest.Status.PENDING,
    ).exists():
        raise ValidationError('You already have a pending change request for this field.')

    request = OrganizationChangeRequest.objects.create(
        user=user,
        field_name=field_name,
        current_value=current,
        proposed_value=proposed_value,
    )

    if field_name in EMAIL_FIELDS:
        from emails.tasks import send_recovery_email_confirmation_email_task
        send_recovery_email_confirmation_email_task.delay(str(request.id), generate_recovery_email_confirm_url(request))
    else:
        from emails.tasks import send_new_organization_change_request_notification_task
        send_new_organization_change_request_notification_task.delay(str(request.id))

    return request


def get_my_change_requests(user: User) -> 'QuerySet[OrganizationChangeRequest]':
    return user.organization_change_requests.all()


def get_all_change_requests(status: str = None, user_id: str = None) -> 'QuerySet[OrganizationChangeRequest]':
    qs = OrganizationChangeRequest.objects.select_related('user', 'user__organization', 'reviewed_by')
    if status:
        qs = qs.filter(status=status)
    if user_id:
        qs = qs.filter(user_id=user_id)
    return qs


def _get_pending(request_id: str) -> OrganizationChangeRequest:
    try:
        request = OrganizationChangeRequest.objects.select_related('user', 'user__organization').get(id=request_id)
    except OrganizationChangeRequest.DoesNotExist:
        raise ValidationError('Change request not found.')
    if request.status != OrganizationChangeRequest.Status.PENDING:
        raise ValidationError('This request has already been reviewed.')
    return request


def _write_proposed_value(request: OrganizationChangeRequest) -> None:
    """Actually applies the change to the real User/Organization field --
    shared by admin approval and the self-service email-confirm path below,
    so the two can never drift on how a field gets written."""
    if request.field_name in USER_FIELDS:
        request.user.phone = request.proposed_value
        request.user.save(update_fields=['phone'])
    else:
        org = request.user.organization
        setattr(org, request.field_name, request.proposed_value)
        org.save(update_fields=[request.field_name])


def _mark_approved(request: OrganizationChangeRequest, reviewed_by: User = None) -> None:
    with transaction.atomic():
        request.status = OrganizationChangeRequest.Status.APPROVED
        request.reviewed_by = reviewed_by
        request.reviewed_at = timezone.now()
        request.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
        _write_proposed_value(request)


def approve_change_request(request_id: str, admin_user: User) -> OrganizationChangeRequest:
    from emails.tasks import send_organization_change_request_reviewed_email_task

    request = _get_pending(request_id)
    if request.field_name in EMAIL_FIELDS:
        raise ValidationError(
            'Recovery email changes are confirmed by the new address itself, not by an admin -- '
            'nothing to approve here. You can still reject it if it looks suspicious.'
        )
    _mark_approved(request, reviewed_by=admin_user)

    send_organization_change_request_reviewed_email_task.delay(str(request.id))
    return request


def confirm_recovery_email_change(token: str) -> OrganizationChangeRequest:
    """Self-service approval for a pending recovery-email change -- reached
    by clicking the link sent to the *proposed* address (see
    generate_recovery_email_confirm_url), not by an admin. Proving control
    of that inbox is the entire trust check; there is no separate review
    step for these two fields (see EMAIL_FIELDS)."""
    from emails.tasks import send_organization_change_request_reviewed_email_task

    try:
        request_id = signing.loads(token, salt=RECOVERY_EMAIL_CONFIRM_SALT, max_age=RECOVERY_EMAIL_CONFIRM_MAX_AGE)
    except signing.SignatureExpired:
        raise ValidationError('This confirmation link has expired. Please request the change again.')
    except signing.BadSignature:
        raise ValidationError('Invalid confirmation link.')

    request = _get_pending(request_id)
    if request.field_name not in EMAIL_FIELDS:
        raise ValidationError('This confirmation link is not valid for that type of change.')

    _mark_approved(request, reviewed_by=None)

    send_organization_change_request_reviewed_email_task.delay(str(request.id))
    return request


def reject_change_request(request_id: str, admin_user: User, reason: str = '') -> OrganizationChangeRequest:
    from emails.tasks import send_organization_change_request_reviewed_email_task

    request = _get_pending(request_id)
    request.status = OrganizationChangeRequest.Status.REJECTED
    request.rejection_reason = reason
    request.reviewed_by = admin_user
    request.reviewed_at = timezone.now()
    request.save(update_fields=['status', 'rejection_reason', 'reviewed_by', 'reviewed_at'])

    send_organization_change_request_reviewed_email_task.delay(str(request.id))
    return request
