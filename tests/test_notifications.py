from django.core import mail
from django.http import Http404
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User
from apps.notifications.models import Notification
import services.notification_service as notification_service


def make_user(**kwargs):
    defaults = {'email': f'user{User.objects.count()}@example.com', 'password': 'pass'}
    defaults.update(kwargs)
    return User.objects.create_user(**defaults)


def make_notification(user, **kwargs):
    defaults = {
        'notification_type': Notification.Type.DONATION_RECEIVED,
        'title': 'Test notification',
        'message': 'Something happened.',
    }
    defaults.update(kwargs)
    return Notification.objects.create(user=user, **defaults)


class CreateNotificationTest(APITestCase):
    def test_create_notification_sets_all_fields(self):
        user = make_user()
        notification = notification_service.create_notification(
            user, Notification.Type.GOAL_REACHED, 'Goal!', 'You hit your goal.', link='/x',
        )
        self.assertEqual(notification.user, user)
        self.assertEqual(notification.notification_type, Notification.Type.GOAL_REACHED)
        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)


class GetUserNotificationsTest(APITestCase):
    def test_only_returns_the_given_users_notifications(self):
        user = make_user()
        other = make_user()
        mine = make_notification(user)
        make_notification(other)

        results = list(notification_service.get_user_notifications(user))
        self.assertEqual(results, [mine])

    def test_is_read_filter(self):
        user = make_user()
        unread = make_notification(user)
        read = make_notification(user, is_read=True)

        self.assertEqual(list(notification_service.get_user_notifications(user, is_read=False)), [unread])
        self.assertEqual(list(notification_service.get_user_notifications(user, is_read=True)), [read])
        self.assertEqual(len(notification_service.get_user_notifications(user)), 2)

    def test_ordered_newest_first(self):
        user = make_user()
        first = make_notification(user, title='First')
        second = make_notification(user, title='Second')
        self.assertEqual(list(notification_service.get_user_notifications(user)), [second, first])


class MarkReadTest(APITestCase):
    def test_marks_unread_notification_as_read(self):
        user = make_user()
        notification = make_notification(user)
        notification_service.mark_read(user, notification.id)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_is_idempotent_on_an_already_read_notification(self):
        from django.utils import timezone
        user = make_user()
        fixed_read_at = timezone.now() - timezone.timedelta(days=1)
        notification = make_notification(user, is_read=True, read_at=fixed_read_at)

        notification_service.mark_read(user, notification.id)

        notification.refresh_from_db()
        # Should not overwrite the original read_at with a fresh timestamp.
        self.assertEqual(notification.read_at, fixed_read_at)

    def test_cannot_mark_another_users_notification_as_read(self):
        owner = make_user()
        other = make_user()
        notification = make_notification(owner)
        with self.assertRaises(Http404):
            notification_service.mark_read(other, notification.id)
        notification.refresh_from_db()
        self.assertFalse(notification.is_read)


class MarkAllReadTest(APITestCase):
    def test_marks_only_the_given_users_unread_notifications(self):
        user = make_user()
        other = make_user()
        mine_unread = make_notification(user)
        mine_read = make_notification(user, is_read=True)
        others_unread = make_notification(other)

        notification_service.mark_all_read(user)

        mine_unread.refresh_from_db()
        others_unread.refresh_from_db()
        self.assertTrue(mine_unread.is_read)
        self.assertFalse(others_unread.is_read)


class UnreadCountTest(APITestCase):
    def test_counts_only_unread(self):
        user = make_user()
        make_notification(user)
        make_notification(user)
        make_notification(user, is_read=True)
        self.assertEqual(notification_service.get_unread_count(user), 2)


class NotifyEmailTest(APITestCase):
    def test_notify_user_sends_to_their_email(self):
        mail.outbox = []
        user = make_user(email='notify-me@example.com')
        notification_service.notify_user(user, 'Subject', 'Body text')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('notify-me@example.com', mail.outbox[0].to)
        self.assertEqual(mail.outbox[0].subject, 'Subject')

    def test_notify_admin_sends_to_contact_email_with_admin_prefix(self):
        from django.conf import settings
        mail.outbox = []
        notification_service.notify_admin('Something happened', 'Details here')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(settings.CONTACT_EMAIL, mail.outbox[0].to)
        self.assertIn('[Admin]', mail.outbox[0].subject)


class NotificationViewTest(APITestCase):
    def setUp(self):
        self.user = make_user(email='viewer@example.com')

    def test_list_requires_auth(self):
        response = self.client.get('/api/v1/notifications/')
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_authenticated_user_only_sees_their_own_notifications(self):
        make_notification(self.user, title='Mine')
        make_notification(make_user(), title='Not mine')

        self.client.force_authenticate(self.user)
        response = self.client.get('/api/v1/notifications/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [n['title'] for n in response.data['results']]
        self.assertEqual(titles, ['Mine'])

    def test_unread_count_endpoint(self):
        make_notification(self.user)
        make_notification(self.user, is_read=True)
        self.client.force_authenticate(self.user)
        response = self.client.get('/api/v1/notifications/unread-count/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['unread_count'], 1)

    def test_mark_read_endpoint(self):
        notification = make_notification(self.user)
        self.client.force_authenticate(self.user)
        response = self.client.post(f'/api/v1/notifications/{notification.id}/read/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_mark_read_on_someone_elses_notification_404s(self):
        notification = make_notification(make_user())
        self.client.force_authenticate(self.user)
        response = self.client.post(f'/api/v1/notifications/{notification.id}/read/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_mark_all_read_endpoint(self):
        make_notification(self.user)
        make_notification(self.user)
        self.client.force_authenticate(self.user)
        response = self.client.post('/api/v1/notifications/mark-all-read/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(notification_service.get_unread_count(self.user), 0)
