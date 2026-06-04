from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.users.models import User


class MeViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='me@example.com',
            password='StrongPass@1',
            first_name='John',
            last_name='Doe',
        )
        self.client.force_authenticate(user=self.user)
        self.url = reverse('user-me')

    def test_get_me(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'me@example.com')

    def test_update_me(self):
        response = self.client.patch(self.url, {'first_name': 'Jane'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Jane')

    def test_unauthenticated_access(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserListViewTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@example.com',
            password='Admin@1234',
            is_staff=True,
            role=User.Role.ADMIN,
        )
        self.regular = User.objects.create_user(
            email='regular@example.com',
            password='User@1234',
        )
        self.url = reverse('user-list')

    def test_admin_can_list_users(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_regular_user_cannot_list_users(self):
        self.client.force_authenticate(user=self.regular)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
