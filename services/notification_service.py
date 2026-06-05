from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework import status
from apps.users.models import User
from emails.service import email_service


def success_response(data, message='Success.', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'message': message, 'data': data}, status=status_code)


def get_user_notifications(user):
    from apps.notifications.models import Notification
    return Notification.objects.filter(user=user).order_by('-created_at')


def mark_read(user, notification_id):
    from apps.notifications.models import Notification
    notification = get_object_or_404(Notification, pk=notification_id, user=user)
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=['is_read', 'read_at'])


def mark_all_read(user):
    from apps.notifications.models import Notification
    Notification.objects.filter(user=user, is_read=False).update(
        is_read=True,
        read_at=timezone.now(),
    )


def get_unread_count(user):
    from apps.notifications.models import Notification
    return Notification.objects.filter(user=user, is_read=False).count()


def create_notification(user, notification_type, title, message, link=''):
    from apps.notifications.models import Notification
    return Notification.objects.create(
        user=user,
        notification_type=notification_type,
        title=title,
        message=message,
        link=link,
    )


def notify_user(user: User, subject: str, message: str) -> None:
    email_service.send_plain_email(
        to=user.email,
        subject=subject,
        message=message,
    )


def notify_admin(subject: str, message: str) -> None:
    from django.conf import settings
    email_service.send_plain_email(
        to=settings.CONTACT_EMAIL,
        subject=f'[Admin] {subject}',
        message=message,
    )
