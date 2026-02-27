# accounts/views.py
from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import UserSerializer, RegisterSerializer, LoginSerializer
from django.contrib.sites.shortcuts import get_current_site
from django.urls import reverse
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import jwt
import logging
from datetime import datetime, timedelta
from .models import CustomUser as User, UserProfile  # Import your custom User model
from django.db import transaction
from django.template.response import TemplateResponse
from django.shortcuts import render
# Add these imports to the existing imports
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from datetime import datetime, timedelta


logger = logging.getLogger(__name__)

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, *args, **kwargs):
        # Debug incoming request
        logger.debug(f"Registration request received: {request.data}")
        
        # Check if email already exists before even starting serializer validation
        email = request.data.get('email')
        if email and User.objects.filter(email=email).exists():
            return Response({
                'error': 'A user with this email already exists. Please use a different email or try to log in.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Use a transaction to ensure all database operations succeed or fail together
            with transaction.atomic():
                serializer = self.serializer_class(data=request.data)
                if serializer.is_valid():
                    user = serializer.save()
                    
                    # Save user_type in the UserProfile model
                    user_type = request.data.get('user_type')
                    if user_type:
                        # Use get_or_create with defaults to avoid duplication
                        profile, created = UserProfile.objects.get_or_create(
                            user=user,
                            defaults={'user_type': user_type, 'terms_agreed': request.data.get('terms_agreed', False)}
                        )
                        
                        # Only update if not created to avoid overwriting
                        if not created:
                            profile.user_type = user_type
                            profile.terms_agreed = request.data.get('terms_agreed', False)
                            profile.save()
                    
                    # Mark user as inactive until email is verified
                    user.is_active = False
                    user.save()
                    
                    # Generate verification token
                    token = self.generate_verification_token(user)
                    
                    try:
                        # Send verification email
                        self.send_verification_email(user, request, token)
                        
                        return Response({
                            'success': True,
                            'message': 'Registration successful. Please check your email to verify your account.'
                        }, status=status.HTTP_201_CREATED)
                    except Exception as email_error:
                        # Log email sending error
                        logger.error(f"Failed to send verification email: {str(email_error)}")
                        # Since we're in a transaction, a raised exception will roll back user creation
                        raise
                
                # Log validation errors
                logger.warning(f"Validation errors: {serializer.errors}")
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            # Log any unexpected errors
            logger.error(f"Unexpected error in registration: {str(e)}")
            return Response({
                'error': 'An unexpected error occurred. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def generate_verification_token(self, user):
        """Generate JWT token for email verification"""
        token_payload = {
            'user_id': user.id,
            'email': user.email,
            'exp': datetime.utcnow() + timedelta(days=1)  # Token expires in 24 hours
        }
        token = jwt.encode(token_payload, settings.SECRET_KEY, algorithm='HS256')
        return token
        
    def send_verification_email(self, user, request, token):
        """Send verification email to user with HTML template"""
        try:
            current_site = get_current_site(request).domain
            relative_url = reverse('verify-email')
            verification_url = f'http://{current_site}{relative_url}?token={token}'
            
            context = {
                'user': user,
                'verification_url': verification_url
            }
            
            # Render email templates
            html_message = render_to_string('email/verification_email.html', context)
            plain_message = strip_tags(html_message)
            
            subject = 'Verify Your Email Address'
            
            email = EmailMessage(
                subject=subject,
                body=html_message,  # Send HTML content
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email]
            )
            email.content_subtype = 'html'  # Mark email as HTML
            logger.debug(f"Sending verification email to {user.email}")
            email.send()
            logger.debug(f"Verification email sent successfully to {user.email}")
        except Exception as e:
            logger.error(f"Email sending error details: {e}")
            raise

class VerifyEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        token = request.GET.get('token')
        if not token:
            return Response({'error': 'No verification token provided'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Decode the token
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            user_id = payload['user_id']

            # Find the user
            user = User.objects.get(id=user_id)

            # Get frontend login URL
            login_url = settings.FRONTEND_URL + 'login'
            
            # Activate the account if not already active
            if not user.is_active:
                user.is_active = True
                user.save()
                
                # Log the successful activation
                logger.info(f"User {user.email} has been verified and activated")

                # Send welcome email
                try:
                    self.send_welcome_email(user, login_url)
                except Exception as email_error:
                    logger.error(f"Failed to send welcome email: {str(email_error)}")
                    # Continue even if welcome email fails
            
            # Redirect directly to the login page
            from django.shortcuts import redirect
            return redirect(login_url)

        except jwt.ExpiredSignatureError:
            logger.warning(f"Expired verification token used: {token[:10]}...")
            return Response({'error': 'Verification link has expired.'}, status=status.HTTP_400_BAD_REQUEST)
        except (jwt.DecodeError, User.DoesNotExist):
            logger.warning(f"Invalid verification token used: {token[:10]}...")
            return Response({'error': 'Invalid verification token.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Verification error: {str(e)}")
            return Response({'error': f'An error occurred: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def send_welcome_email(self, user, login_url):
        """Send a welcome email to the user after successful verification"""
        context = {
            'user': user,
            'login_url': login_url
        }
        
        # Render email templates
        html_message = render_to_string('email/welcome_email.html', context)
        plain_message = strip_tags(html_message)
        
        # Send email
        email = EmailMessage(
            subject='Welcome to Your Dreams Academy!',
            body=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email]
        )
        email.content_subtype = 'html'  
        email.send()
        logger.info(f"Welcome email sent to {user.email}")

class ResendVerificationEmailView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Find the user
            user = User.objects.get(email=email)
            
            # Check if already verified
            if user.is_active:
                return Response({'info': 'Your email is already verified.'}, status=status.HTTP_200_OK)
            
            # Generate new token
            token = jwt.encode({
                'user_id': user.id,
                'email': user.email,
                'exp': datetime.utcnow() + timedelta(days=1)
            }, settings.SECRET_KEY, algorithm='HS256')
            
            # Send verification email with HTML template
            current_site = get_current_site(request).domain
            relative_url = reverse('verify-email')
            verification_url = f'http://{current_site}{relative_url}?token={token}'
            
            context = {
                'user': user,
                'verification_url': verification_url
            }
            
            # Render email templates - FIXED PATH
            html_message = render_to_string('email/verification_email.html', context)
            plain_message = strip_tags(html_message)
            
            subject = 'Verify Your Email Address'
            
            # Add debugging
            logger.debug(f"Sending verification email to {user.email} with URL: {verification_url}")
            
            email = EmailMessage(
                subject=subject,
                body=html_message,  # Send the HTML message as the body
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email]
            )
            email.content_subtype = 'html'  # Main content is now HTML
            email.send()
            
            logger.debug(f"Email sent successfully to {user.email}")
            
            return Response({
                'success': 'Verification email has been resent. Please check your inbox.'
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            # For security reasons, don't reveal if the email exists or not
            return Response({
                'success': 'If your email exists in our system, a verification link has been sent.'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error sending verification email: {str(e)}")
            return Response({'error': f'An error occurred: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# accounts/views.py
class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        
        # Check if user is active
        if not user.is_active:
            return Response(
                {'detail': 'Account not active. Please verify your email.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Ensure profile exists and has user_type
        profile = user.profile
        if not profile.user_type:
            profile.user_type = 'admin' if user.is_superuser else 'student'
            profile.save()
        
        refresh = RefreshToken.for_user(user)
        
        user_data = {
            'id': user.id,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'profile': {
                'user_type': profile.user_type,
                'terms_agreed': profile.terms_agreed,
            }
        }
        
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': user_data
        })
         
class UserView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
    

# Add these new views for password reset
class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.get(email=email)
            # Generate token for password reset
            token = self.generate_reset_token(user)
            
            # Send password reset email
            self.send_reset_email(user, request, token)
            
            return Response({
                'success': True,
                'message': 'Password reset instructions have been sent to your email.'
            }, status=status.HTTP_200_OK)
            
        except User.DoesNotExist:
            # For security reasons, don't reveal if the email exists or not
            return Response({
                'success': True,
                'message': 'If your email exists in our system, password reset instructions have been sent.'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error sending password reset email: {str(e)}")
            return Response({
                'error': 'An unexpected error occurred. Please try again.'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def generate_reset_token(self, user):
        """Generate JWT token for password reset"""
        token_payload = {
            'user_id': user.id,
            'email': user.email,
            'exp': datetime.utcnow() + timedelta(hours=1)  # Token expires in 1 hour
        }
        token = jwt.encode(token_payload, settings.SECRET_KEY, algorithm='HS256')
        return token
        
    def send_reset_email(self, user, request, token):
        """Send password reset email to user with HTML template"""
        try:
            current_site = get_current_site(request).domain
            reset_url = f"{settings.FRONTEND_URL}reset-password?token={token}"
            
            context = {
                'user': user,
                'reset_url': reset_url
            }
            
            # Render email templates
            html_message = render_to_string('email/password_reset_email.html', context)
            plain_message = strip_tags(html_message)
            
            subject = 'Reset Your Password'
            
            email = EmailMessage(
                subject=subject,
                body=html_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email]
            )
            email.content_subtype = 'html'
            logger.debug(f"Sending password reset email to {user.email}")
            email.send()
            logger.debug(f"Password reset email sent successfully to {user.email}")
        except Exception as e:
            logger.error(f"Email sending error details: {e}")
            raise

class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        token = request.data.get('token')
        new_password = request.data.get('password')
        
        if not token or not new_password:
            return Response({
                'error': 'Token and new password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            # Decode the token
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
            user_id = payload['user_id']
            
            # Find the user
            user = User.objects.get(id=user_id)
            
            # Set the new password
            user.set_password(new_password)
            user.save()
            
            # Ensure the user account is active
            if not user.is_active:
                user.is_active = True
                user.save()
            
            logger.info(f"Password reset successful for user {user.email}")
            
            return Response({
                'success': True,
                'message': 'Your password has been reset successfully. You can now log in with your new password.'
            }, status=status.HTTP_200_OK)
            
        except jwt.ExpiredSignatureError:
            logger.warning(f"Expired password reset token used")
            return Response({
                'error': 'Password reset link has expired. Please request a new one.'
            }, status=status.HTTP_400_BAD_REQUEST)
        except (jwt.DecodeError, User.DoesNotExist):
            logger.warning(f"Invalid password reset token used")
            return Response({
                'error': 'Invalid password reset token.'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Password reset error: {str(e)}")
            return Response({
                'error': f'An error occurred: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)    