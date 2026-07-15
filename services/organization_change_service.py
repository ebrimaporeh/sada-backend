from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.users.models import User, OrganizationChangeRequest

# phone lives on User itself; the other three live on the related Organization
# profile — this map is how approve_change_request() knows where to write.
USER_FIELDS = {OrganizationChangeRequest.Field.PHONE}


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


def approve_change_request(request_id: str, admin_user: User) -> OrganizationChangeRequest:
    from emails.tasks import send_organization_change_request_reviewed_email_task

    with transaction.atomic():
        request = _get_pending(request_id)
        request.status = OrganizationChangeRequest.Status.APPROVED
        request.reviewed_by = admin_user
        request.reviewed_at = timezone.now()
        request.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

        if request.field_name in USER_FIELDS:
            request.user.phone = request.proposed_value
            request.user.save(update_fields=['phone'])
        else:
            org = request.user.organization
            setattr(org, request.field_name, request.proposed_value)
            org.save(update_fields=[request.field_name])

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
