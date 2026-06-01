# apps/users/services.py
#
# All user/auth business logic lives here.
# Views call these methods — they never touch models or send emails directly.
#
import jwt
import logging
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags

from .models import CustomUser, UserProfile

logger = logging.getLogger(__name__)


class TokenService:
    """Handles JWT token generation and decoding for email flows."""

    ALGORITHM = 'HS256'

    @staticmethod
    def generate_verification_token(user: CustomUser) -> str:
        payload = {
            'user_id': user.id,
            'email': user.email,
            'exp': datetime.utcnow() + timedelta(days=1),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=TokenService.ALGORITHM)

    @staticmethod
    def generate_password_reset_token(user: CustomUser) -> str:
        payload = {
            'user_id': user.id,
            'email': user.email,
            'exp': datetime.utcnow() + timedelta(hours=1),
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=TokenService.ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> dict:
        """Decode and return payload. Raises jwt.ExpiredSignatureError or jwt.DecodeError."""
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[TokenService.ALGORITHM])


class EmailService:
    """Handles all outgoing transactional emails for the users app."""

    @staticmethod
    def send_verification_email(user: CustomUser, request, token: str):
        current_site = get_current_site(request).domain
        relative_url = reverse('verify-email')
        verification_url = f'http://{current_site}{relative_url}?token={token}'

        html_message = render_to_string('email/verification_email.html', {
            'user': user,
            'verification_url': verification_url,
        })

        EmailService._send(
            subject='Verify Your Email Address',
            html_body=html_message,
            to=user.email,
        )
        logger.info(f"Verification email sent to {user.email}")

    @staticmethod
    def send_welcome_email(user: CustomUser, login_url: str):
        html_message = render_to_string('email/welcome_email.html', {
            'user': user,
            'login_url': login_url,
        })

        EmailService._send(
            subject='Welcome to Dreams Academy!',
            html_body=html_message,
            to=user.email,
        )
        logger.info(f"Welcome email sent to {user.email}")

    @staticmethod
    def send_password_reset_email(user: CustomUser, token: str):
        reset_url = f"{settings.FRONTEND_URL}reset-password?token={token}"

        html_message = render_to_string('email/password_reset_email.html', {
            'user': user,
            'reset_url': reset_url,
        })

        EmailService._send(
            subject='Reset Your Password',
            html_body=html_message,
            to=user.email,
        )
        logger.info(f"Password reset email sent to {user.email}")

    @staticmethod
    def _send(subject: str, html_body: str, to: str):
        """Internal send helper. All emails go through here."""
        email = EmailMessage(
            subject=subject,
            body=html_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to],
        )
        email.content_subtype = 'html'
        email.send()


class UserService:
    """Handles user registration, verification, and profile management."""

    @staticmethod
    def register(validated_data: dict, request) -> CustomUser:
        """
        Create a new inactive user + profile, then send a verification email.
        Raises on email send failure (rolls back via the view's transaction.atomic).
        """
        user = CustomUser.objects.create_user(
            email=validated_data['email'],
            first_name=validated_data['first_name'],
            last_name=validated_data['last_name'],
            password=validated_data['password'],
        )

        # Mark inactive until email is verified
        user.is_active = False
        user.save(update_fields=['is_active'])

        # Set profile fields that came from the registration form
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.user_type = validated_data.get('user_type', 'student')
        profile.terms_agreed = validated_data.get('terms_agreed', False)
        profile.save(update_fields=['user_type', 'terms_agreed'])

        token = TokenService.generate_verification_token(user)
        EmailService.send_verification_email(user, request, token)

        return user

    @staticmethod
    def verify_email(token: str) -> CustomUser:
        """
        Decode verification token and activate the user account.
        Returns the activated user.
        Raises jwt.ExpiredSignatureError, jwt.DecodeError, or CustomUser.DoesNotExist.
        """
        payload = TokenService.decode_token(token)
        user = CustomUser.objects.get(id=payload['user_id'])

        if not user.is_active:
            user.is_active = True
            user.save(update_fields=['is_active'])
            logger.info(f"User {user.email} verified and activated")

            login_url = settings.FRONTEND_URL + 'login'
            try:
                EmailService.send_welcome_email(user, login_url)
            except Exception as e:
                # Welcome email failure is non-critical — log and continue
                logger.error(f"Welcome email failed for {user.email}: {e}")

        return user

    @staticmethod
    def resend_verification(email: str, request) -> None:
        """
        Resend a verification email to an unverified user.
        Silently does nothing if the user is already active (let the view handle messaging).
        Raises CustomUser.DoesNotExist if user not found.
        """
        user = CustomUser.objects.get(email=email)

        if user.is_active:
            return  # Already verified — view will return a friendly message

        token = TokenService.generate_verification_token(user)
        EmailService.send_verification_email(user, request, token)

    @staticmethod
    def request_password_reset(email: str) -> None:
        """
        Generate and send a password reset email.
        Raises CustomUser.DoesNotExist if not found (caller should handle silently for security).
        """
        user = CustomUser.objects.get(email=email)
        token = TokenService.generate_password_reset_token(user)
        EmailService.send_password_reset_email(user, token)

    @staticmethod
    def reset_password(token: str, new_password: str) -> CustomUser:
        """
        Validate token and set a new password.
        Raises jwt.ExpiredSignatureError, jwt.DecodeError, or CustomUser.DoesNotExist.
        """
        payload = TokenService.decode_token(token)
        user = CustomUser.objects.get(id=payload['user_id'])

        user.set_password(new_password)
        if not user.is_active:
            user.is_active = True
        user.save()

        logger.info(f"Password reset successful for {user.email}")
        return user

    @staticmethod
    def ensure_profile_user_type(user: CustomUser) -> UserProfile:
        """
        Called on login — ensures the profile always has a user_type set.
        Returns the profile.
        """
        profile = user.profile
        if not profile.user_type:
            profile.user_type = user._default_user_type()
            profile.save(update_fields=['user_type'])
        return profile