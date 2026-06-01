from django.test import TestCase

# Create your tests here.
# apps/users/tests/test_services.py
#
# Unit tests for UserService — no HTTP context needed,
# just call the service methods directly.
from django.test import TestCase
from unittest.mock import patch

from apps.users.models import CustomUser, UserProfile
from apps.users.services import TokenService, UserService


class TestTokenService(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email='test@example.com',
            password='testpass123',
        )

    def test_generate_and_decode_verification_token(self):
        token = TokenService.generate_verification_token(self.user)
        payload = TokenService.decode_token(token)
        self.assertEqual(payload['user_id'], self.user.id)
        self.assertEqual(payload['email'], self.user.email)

    def test_generate_and_decode_reset_token(self):
        token = TokenService.generate_password_reset_token(self.user)
        payload = TokenService.decode_token(token)
        self.assertEqual(payload['user_id'], self.user.id)


class TestUserService(TestCase):

    @patch('apps.users.services.EmailService.send_verification_email')
    def test_register_creates_inactive_user(self, mock_email):
        data = {
            'email': 'newuser@example.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password': 'securepass123',
            'user_type': 'student',
            'terms_agreed': True,
        }
        user = UserService.register(data, request=None)

        self.assertFalse(user.is_active)
        self.assertEqual(user.user_profile.user_type, 'student')
        self.assertTrue(user.user_profile.terms_agreed)
        mock_email.assert_called_once()

    @patch('apps.users.services.EmailService.send_welcome_email')
    def test_verify_email_activates_user(self, mock_welcome):
        user = CustomUser.objects.create_user(email='verify@example.com', password='pass')
        user.is_active = False
        user.save()

        token = TokenService.generate_verification_token(user)
        activated = UserService.verify_email(token)

        activated.refresh_from_db()
        self.assertTrue(activated.is_active)

    def test_reset_password_sets_new_password(self):
        user = CustomUser.objects.create_user(email='reset@example.com', password='oldpass')
        token = TokenService.generate_password_reset_token(user)

        UserService.reset_password(token, 'newpass456')
        user.refresh_from_db()
        self.assertTrue(user.check_password('newpass456'))