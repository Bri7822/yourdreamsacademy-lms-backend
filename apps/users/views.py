from django.shortcuts import render

# Create your views here.
# apps/users/views.py
#
# THIN VIEWS — each view does exactly:
#   1. Validate input (serializer)
#   2. Call service
#   3. Handle exceptions → HTTP status codes
#   4. Return response
#
# Zero business logic here.
#
import jwt
import logging

from django.db import transaction
from django.shortcuts import redirect

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from django.conf import settings

from .models import CustomUser
from .serializers import LoginSerializer, RegisterSerializer, UserSerializer
from .services import UserService

logger = logging.getLogger(__name__)


class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # Quick duplicate-email check before running full validation
        email = request.data.get('email', '').strip()
        if email and CustomUser.objects.filter(email=email).exists():
            return Response(
                {'error': 'An account with this email already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                UserService.register(serializer.validated_data, request)
        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return Response(
                {'error': 'Registration failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {'message': 'Registration successful. Please check your email to verify your account.'},
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        token = request.GET.get('token')
        if not token:
            return Response({'error': 'No verification token provided.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            UserService.verify_email(token)
            return redirect(settings.FRONTEND_URL + 'login')

        except jwt.ExpiredSignatureError:
            return Response({'error': 'Verification link has expired.'}, status=status.HTTP_400_BAD_REQUEST)
        except (jwt.DecodeError, CustomUser.DoesNotExist):
            return Response({'error': 'Invalid verification token.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Email verification error: {e}")
            return Response({'error': 'An unexpected error occurred.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ResendVerificationEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip()
        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            UserService.resend_verification(email, request)
        except CustomUser.DoesNotExist:
            # Don't reveal whether the email exists
            pass
        except Exception as e:
            logger.error(f"Resend verification error: {e}")
            return Response({'error': 'Failed to resend email.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {'message': 'If your email is registered and unverified, a new link has been sent.'},
            status=status.HTTP_200_OK,
        )


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        if not user.is_active:
            return Response(
                {'error': 'Account not active. Please verify your email.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        profile = UserService.ensure_profile_user_type(user)
        refresh = RefreshToken.for_user(user)

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'user_type': profile.user_type,
            },
        })


class UserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip()
        if not email:
            return Response({'error': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            UserService.request_password_reset(email)
        except CustomUser.DoesNotExist:
            pass  # Don't reveal whether the email exists
        except Exception as e:
            logger.error(f"Password reset request error: {e}")
            return Response({'error': 'Failed to send reset email.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {'message': 'If your email exists in our system, a password reset link has been sent.'},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        token = request.data.get('token', '').strip()
        new_password = request.data.get('password', '').strip()

        if not token or not new_password:
            return Response(
                {'error': 'Token and new password are required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            UserService.reset_password(token, new_password)
        except jwt.ExpiredSignatureError:
            return Response({'error': 'Reset link has expired. Please request a new one.'}, status=status.HTTP_400_BAD_REQUEST)
        except (jwt.DecodeError, CustomUser.DoesNotExist):
            return Response({'error': 'Invalid reset token.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Password reset confirm error: {e}")
            return Response({'error': 'An unexpected error occurred.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({'message': 'Password reset successful. You can now log in.'}, status=status.HTTP_200_OK)