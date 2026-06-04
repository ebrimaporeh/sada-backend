from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.users.models import User


class RegisterViewTest(APITestCase):
    def setUp(self):
        self.url = reverse('auth-register')
        self.valid_data = {
            'email': 'test@example.com',
            'password': 'StrongPass@1',
            'password_confirm': 'StrongPass@1',
            'first_name': 'Test',
            'last_name': 'User',
        }

    def test_register_success(self):
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertIn('tokens', response.data['data'])
        self.assertTrue(User.objects.filter(email='test@example.com').exists())

    def test_register_duplicate_email(self):
        User.objects.create_user(email='test@example.com', password='pass')
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_register_password_mismatch(self):
        data = {**self.valid_data, 'password_confirm': 'WrongPass@1'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginViewTest(APITestCase):
    def setUp(self):
        self.url = reverse('auth-login')
        self.user = User.objects.create_user(
            email='login@example.com',
            password='StrongPass@1',
        )

    def test_login_success(self):
        response = self.client.post(self.url, {
            'email': 'login@example.com',
            'password': 'StrongPass@1',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('access', response.data['data']['tokens'])

    def test_login_wrong_password(self):
        response = self.client.post(self.url, {
            'email': 'login@example.com',
            'password': 'WrongPass@1',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
