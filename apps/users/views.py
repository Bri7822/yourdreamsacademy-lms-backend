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
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction, IntegrityError 
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.filters import SearchFilter, OrderingFilter
 
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import rest_framework as filters
from django.conf import settings

from .models import CustomUser, UserProfile, Course, Enrollment, AutoApprovalSettings
from .serializers import (
    LoginSerializer, 
    RegisterSerializer, UserSerializer,
    TeacherSerializer,
    CourseSerializer,
    StudentSerializer,
    EnrollmentSerializer,
    EnrollmentCreateSerializer,
    EnrollmentCourseSerializer,
    AutoApprovalSettingsSerializer,
)
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
                        'profile': {                          
                            'user_type': profile.user_type,
                            'terms_agreed': profile.terms_agreed,
                        },
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

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
 
class UserFilter(filters.FilterSet):
    user_type = filters.CharFilter(field_name='user_profile__user_type')
 
    class Meta:
        model = CustomUser
        fields = ['is_active', 'user_type']
 
 
class UserManagementView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = UserFilter
    search_fields = ['email', 'first_name', 'last_name']
    ordering_fields = ['date_joined', 'email']
    ordering = ['-date_joined']
 
    def get_queryset(self):
        return CustomUser.objects.all().select_related('user_profile')
 
 
class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = UserSerializer
    queryset = CustomUser.objects.all().select_related('user_profile')
 
    def perform_update(self, serializer):
        user = serializer.save()
        user_type = self.request.data.get('user_type')
        if user_type:
            user.user_profile.user_type = user_type
            user.user_profile.save()
 
    def destroy(self, request, *args, **kwargs):
        self.perform_destroy(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)
 
 
class BulkUserActionsView(generics.GenericAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = UserSerializer
 
    def post(self, request, *args, **kwargs):
        action = request.data.get('action')
        user_ids = request.data.get('user_ids', [])
 
        if not action or not user_ids:
            return Response(
                {'error': 'Action and user_ids are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        users = CustomUser.objects.filter(id__in=user_ids)
        if action == 'activate':
            users.update(is_active=True)
        elif action == 'deactivate':
            users.update(is_active=False)
        elif action == 'delete':
            users.delete()
        else:
            return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)
 
        return Response({'success': f'{users.count()} users {action}d'})
 
 
# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------
 
class CourseFilter(filters.FilterSet):
    is_active = filters.BooleanFilter()
    teacher = filters.NumberFilter(field_name='teacher__id')
    min_price = filters.NumberFilter(field_name='price', lookup_expr='gte')
    max_price = filters.NumberFilter(field_name='price', lookup_expr='lte')
 
    class Meta:
        model = Course
        fields = ['is_active', 'teacher']
 
 
class CourseManagementView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = CourseSerializer
    queryset = Course.objects.all().select_related('teacher__user')
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = CourseFilter
    search_fields = ['title', 'description']
    ordering_fields = ['title', 'price', 'created_at']
    ordering = ['-created_at']
 
    def perform_create(self, serializer):
        serializer.save(teacher=None)
 
 
class CourseDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = CourseSerializer
    queryset = Course.objects.all().select_related('teacher__user')
 
 
class TeacherListView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = TeacherSerializer
    queryset = UserProfile.objects.filter(user_type='teacher').select_related('user')
    filter_backends = [SearchFilter]
    search_fields = ['user__first_name', 'user__last_name', 'user__email']
 
 
class BulkCourseActionsView(generics.GenericAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = CourseSerializer
 
    def post(self, request, *args, **kwargs):
        action = request.data.get('action')
        course_ids = request.data.get('course_ids', [])
 
        if not action or not course_ids:
            return Response(
                {'error': 'Action and course_ids are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
 
        courses = Course.objects.filter(id__in=course_ids)
        if action == 'activate':
            courses.update(is_active=True)
        elif action == 'deactivate':
            courses.update(is_active=False)
        elif action == 'delete':
            courses.delete()
        else:
            return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)
 
        return Response({'success': f'{courses.count()} courses {action}d'})
 
 
# ---------------------------------------------------------------------------
# Enrollments
# ---------------------------------------------------------------------------
 
class EnrollmentListView(APIView):
    permission_classes = [permissions.IsAdminUser]
 
    def get(self, request):
        try:
            enrollments = Enrollment.objects.select_related(
                'student', 'course', 'student__user_profile'
            ).all()
            data = []
            for e in enrollments:
                data.append({
                    'id': e.id,
                    'student': e.student.id,
                    'student_name': e.student_name,
                    'student_email': e.student_email,
                    'course': e.course.id,
                    'course_title': e.course_title,
                    'course_code': e.course_code,
                    'status': e.status,
                    'enrolled_at': e.enrolled_at,
                    'completed_at': e.completed_at,
                    'progress': e.progress,
                    'exercises_completed': e.exercises_completed,
                    'exercises_total': e.exercises_total,
                    'notes': e.notes,
                })
            return Response(data)
        except Exception as e:
            logger.error(f"Error fetching enrollments: {str(e)}", exc_info=True)
            return Response({'error': 'Failed to fetch enrollments'}, status=500)
 
 
class StudentListView(APIView):
    permission_classes = [permissions.IsAdminUser]
 
    def get(self, request):
        try:
            students = CustomUser.objects.select_related('user_profile').filter(
                user_profile__user_type='student', is_active=True
            ).order_by('first_name', 'last_name')
            data = [
                {
                    'id': s.id,
                    'first_name': s.first_name,
                    'last_name': s.last_name,
                    'email': s.email,
                    'full_name': s.get_full_name(),
                    'total_enrollments': s.enrollments.count(),
                    'completed_courses': s.enrollments.filter(status='completed').count(),
                }
                for s in students
            ]
            return Response(data)
        except Exception as e:
            logger.error(f"Error fetching students: {str(e)}", exc_info=True)
            return Response({'error': 'Failed to fetch students'}, status=500)
 
 
class CourseListView(APIView):
    permission_classes = [permissions.IsAdminUser]
 
    def get(self, request):
        try:
            courses = Course.objects.filter(is_active=True).order_by('title')
            serializer = EnrollmentCourseSerializer(courses, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error fetching courses: {str(e)}", exc_info=True)
            return Response({'error': 'Failed to fetch courses'}, status=500)
 
 
class EnrollmentCreateView(APIView):
    permission_classes = [permissions.IsAdminUser]
 
    def post(self, request):
        student_id = request.data.get('student')
        course_id = request.data.get('course')
        logger.info(f"Enrollment attempt: student={student_id}, course={course_id}")
 
        if not student_id or not course_id:
            return Response({'error': 'Both student and course are required'}, status=400)
 
        try:
            student_id = int(student_id)
            course_id = int(course_id)
        except (ValueError, TypeError):
            return Response({'error': 'Invalid student or course ID format'}, status=400)
 
        try:
            with transaction.atomic():
                try:
                    student = CustomUser.objects.select_related('user_profile').get(id=student_id)
                except CustomUser.DoesNotExist:
                    return Response({'error': 'Student does not exist'}, status=400)
 
                if not hasattr(student, 'user_profile'):
                    return Response({'error': 'Selected user has no profile'}, status=400)
                if student.user_profile.user_type != 'student':
                    return Response({'error': 'Selected user is not a student'}, status=400)
 
                try:
                    course = Course.objects.get(id=course_id)
                    if not course.is_active:
                        return Response({'error': 'Course is not active'}, status=400)
                except Course.DoesNotExist:
                    return Response({'error': f'Course {course_id} does not exist'}, status=400)
 
                if Enrollment.objects.filter(student_id=student_id, course_id=course_id).exists():
                    return Response({'error': 'Student is already enrolled in this course'}, status=400)
 
                enrollment = Enrollment.objects.create(
                    student_id=student_id,
                    course_id=course_id,
                    status=request.data.get('status', 'pending'),
                    notes=request.data.get('notes', ''),
                )
                return Response({
                    'id': enrollment.id,
                    'student': student.id,
                    'student_name': student.get_full_name(),
                    'student_email': student.email,
                    'course': course.id,
                    'course_title': course.title,
                    'course_code': course.code,
                    'status': enrollment.status,
                    'message': 'Student enrolled successfully!',
                }, status=201)
 
        except IntegrityError as e:
            lower = str(e).lower()
            if 'unique' in lower:
                return Response({'error': 'Student is already enrolled in this course'}, status=400)
            if 'foreign key' in lower:
                return Response({'error': 'Invalid student or course reference'}, status=400)
            return Response({'error': 'Database constraint violation'}, status=500)
        except ValidationError as e:
            return Response({'error': f'Validation error: {str(e)}'}, status=400)
        except Exception as e:
            logger.error(f"Unexpected enrollment error: {str(e)}", exc_info=True)
            return Response({'error': 'An unexpected error occurred'}, status=500)
 
 
class EnrollmentActionView(APIView):
    permission_classes = [permissions.IsAdminUser]
 
    def post(self, request, pk, action):
        try:
            enrollment = get_object_or_404(Enrollment, pk=pk)
 
            if action == 'approve':
                enrollment.status = Enrollment.APPROVED
                enrollment.save()
                message = 'Enrollment approved successfully'
            elif action == 'decline':
                enrollment.status = Enrollment.DECLINED
                enrollment.save()
                message = 'Enrollment declined successfully'
            elif action == 'complete':
                enrollment.status = Enrollment.COMPLETED
                enrollment.completed_at = timezone.now()
                enrollment.save()
                message = 'Enrollment marked as complete'
            elif action == 'reset':
                from apps.students.models import StudentExercise
                StudentExercise.objects.filter(
                    student=enrollment.student, lesson__course=enrollment.course
                ).update(completed=False, completed_at=None, score=0.0)
                enrollment.status = Enrollment.APPROVED
                enrollment.completed_at = None
                enrollment.save()
                message = 'Progress reset successfully'
            else:
                return Response({'error': 'Invalid action'}, status=400)
 
            return Response({'message': message})
        except Exception as e:
            logger.error(f"Error on enrollment action {action}: {str(e)}", exc_info=True)
            return Response({'error': f'Failed to {action} enrollment'}, status=500)
 
 
class EnrollmentProgressDetailView(APIView):
    permission_classes = [permissions.IsAdminUser]
 
    def get(self, request, pk):
        try:
            enrollment = get_object_or_404(
                Enrollment.objects.select_related('student', 'course'), pk=pk
            )
            from apps.quizzes.models import StudentExercise
            exercises = StudentExercise.objects.filter(
                student=enrollment.student, lesson__course=enrollment.course
            ).select_related('lesson').order_by('lesson__order')
 
            exercise_data = [
                {
                    'id': ex.id,
                    'title': ex.lesson.title,
                    'description': ex.lesson.description or '',
                    'completed': ex.completed,
                    'completed_at': ex.completed_at,
                    'score': ex.score,
                }
                for ex in exercises
            ]
 
            return Response({
                'id': enrollment.id,
                'student_name': enrollment.student_name,
                'student_email': enrollment.student_email,
                'course_title': enrollment.course_title,
                'progress': enrollment.progress,
                'exercises': exercise_data,
            })
        except Exception as e:
            logger.error(f"Error fetching enrollment details {pk}: {str(e)}", exc_info=True)
            return Response({'error': 'Failed to load enrollment details'}, status=500)
 
 
class BulkEnrollmentActionsView(APIView):
    permission_classes = [permissions.IsAdminUser]
 
    def post(self, request):
        action = request.data.get('action')
        enrollment_ids = request.data.get('enrollment_ids', [])
 
        if not action or not enrollment_ids:
            return Response({'error': 'Action and enrollment IDs are required'}, status=400)
 
        try:
            with transaction.atomic():
                enrollments = Enrollment.objects.filter(id__in=enrollment_ids)
 
                if action == 'approve':
                    enrollments.update(status=Enrollment.APPROVED)
                elif action == 'decline':
                    enrollments.update(status=Enrollment.DECLINED)
                elif action == 'complete':
                    enrollments.update(status=Enrollment.COMPLETED, completed_at=timezone.now())
                elif action == 'reset':
                    from apps.quizzes.models import StudentExercise
                    for e in enrollments:
                        StudentExercise.objects.filter(
                            student=e.student, lesson__course=e.course
                        ).update(completed=False, completed_at=None, score=0.0)
                    enrollments.update(status=Enrollment.APPROVED, completed_at=None)
                else:
                    return Response({'error': 'Invalid action'}, status=400)
 
                return Response({'message': f'Bulk action {action} completed'})
        except Exception as e:
            logger.error(f"Bulk action {action} failed: {str(e)}", exc_info=True)
            return Response({'error': 'Bulk action failed'}, status=500)
 
 
class AutoApprovalSettingsView(APIView):
    permission_classes = [permissions.IsAdminUser]
 
    def get(self, request):
        settings_obj, _ = AutoApprovalSettings.objects.get_or_create(defaults={'enabled': False})
        return Response({'enabled': settings_obj.enabled})
 
    def post(self, request):
        enabled = request.data.get('enabled', False)
        settings_obj, _ = AutoApprovalSettings.objects.get_or_create(defaults={'enabled': False})
        settings_obj.enabled = enabled
        settings_obj.updated_by = request.user
        settings_obj.save()
        return Response({'enabled': settings_obj.enabled})
 
 
class EnrollmentStatisticsView(APIView):
    permission_classes = [permissions.IsAdminUser]
 
    def get(self, request):
        try:
            return Response({
                'total': Enrollment.objects.count(),
                'pending': Enrollment.objects.filter(status=Enrollment.PENDING).count(),
                'approved': Enrollment.objects.filter(status=Enrollment.APPROVED).count(),
                'completed': Enrollment.objects.filter(status=Enrollment.COMPLETED).count(),
                'declined': Enrollment.objects.filter(status=Enrollment.DECLINED).count(),
            })
        except Exception as e:
            logger.error(f"Error fetching enrollment stats: {str(e)}", exc_info=True)
            return Response({'error': 'Failed to fetch statistics'}, status=500)
 
 
# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
 
class DashboardStatisticsView(APIView):
    permission_classes = [permissions.IsAdminUser]
 
    def get(self, request):
        try:
            return Response({
                'total_users': CustomUser.objects.count(),
                'active_courses': Course.objects.filter(is_active=True).count(),
                'total_enrollments': Enrollment.objects.count(),
                'monthly_revenue': 0,  # Placeholder until Paystack is integrated
            })
        except Exception as e:
            logger.error(f"Dashboard stats error: {str(e)}")
            return Response({'error': 'Failed to fetch dashboard statistics'}, status=500)