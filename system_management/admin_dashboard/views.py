from rest_framework import generics, permissions, status, serializers
from rest_framework.response import Response
from accounts.models import CustomUser, UserProfile, Course
from django.db.models import Q
import django.db.models as models
from django_filters.rest_framework import DjangoFilterBackend, filters
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters import rest_framework as filters
from .serializers import UserSerializer, UserProfileSerializer, CourseSerializer, TeacherSerializer, LessonSerializer,StudentSerializer
from admin_dashboard.models import (
    Lesson, AutoApprovalSettings, Enrollment,
    Transaction, TeacherPayout, RevenueReport
)
from django.db import transaction, IntegrityError
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework import viewsets
import logging
import re
import os
from django.shortcuts import get_object_or_404
from .serializers import (
    EnrollmentCourseSerializer,
    EnrollmentSerializer,
    EnrollmentStudentExerciseSerializer,
    AutoApprovalSettingsSerializer,
    EnrollmentStudentExerciseSerializer,
    AutoApprovalSettingsSerializer,
    EnrollmentCreateSerializer,
    StudentSerializer,
    LessonSerializer,TransactionSerializer,
    TeacherPayoutSerializer, RevenueReportSerializer

)
from django.db.models import Count, Q
from admin_dashboard.models import (Enrollment, AutoApprovalSettings,
 Transaction, TeacherPayout, RevenueReport
)
from student_dashboard.models import StudentExercise
from rest_framework.views import APIView
from django.db.models import Sum, Count, Avg

# testing
from django.shortcuts import render
from django.views import View
from django.utils.decorators import method_decorator
import json
from .paypal_utils import create_paypal_order, capture_paypal_order
from decimal import Decimal
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
import random


logger = logging.getLogger(__name__)

class UserFilter(filters.FilterSet):
    user_type = filters.CharFilter(field_name='user_profile__user_type')

    class Meta:
        model = CustomUser
        fields = ['is_active', 'user_type']

# admin_dashboard/views.py
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
        # Update profile if user_type is provided
        user_type = self.request.data.get('user_type')
        if user_type:
            profile = user.user_profile
            profile.user_type = user_type
            profile.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        # Perform hard delete
        self.perform_destroy(instance)
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
                status=status.HTTP_400_BAD_REQUEST
            )

        users = CustomUser.objects.filter(id__in=user_ids)

        if action == 'activate':
            users.update(is_active=True)
        elif action == 'deactivate':
            users.update(is_active=False)
        elif action == 'delete':
            users.delete()
        else:
            return Response(
                {'error': 'Invalid action'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {'success': f'{len(users)} users {action}d'},
            status=status.HTTP_200_OK
        )

# courses
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
        # Allow course creation without teacher
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
                status=status.HTTP_400_BAD_REQUEST
            )

        courses = Course.objects.filter(id__in=course_ids)

        if action == 'activate':
            courses.update(is_active=True)
        elif action == 'deactivate':
            courses.update(is_active=False)
        elif action == 'delete':
            courses.delete()
        else:
            return Response(
                {'error': 'Invalid action'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {'success': f'{len(courses)} courses {action}d'},
            status=status.HTTP_200_OK
        )

# Add this to your LessonListCreateView to debug the course ID issue
class LessonListCreateView(generics.ListCreateAPIView):
    serializer_class = LessonSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        course_id = self.kwargs.get('course_id')
        return Lesson.objects.filter(
            course_id=course_id
        ).order_by('order')

    def perform_create(self, serializer):
        course_id = self.kwargs.get('course_id')

        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            raise serializers.ValidationError("Course not found")

        # Calculate next order if not provided
        if 'order' not in serializer.validated_data:
            max_order = Lesson.objects.filter(
                course=course
            ).aggregate(models.Max('order'))['order__max'] or 0
            serializer.validated_data['order'] = max_order + 1

        serializer.save(course=course)

class LessonRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LessonSerializer
    permission_classes = [permissions.IsAdminUser]
    lookup_field = 'id'

    def get_queryset(self):
        return Lesson.objects.filter(course_id=self.kwargs['course_id'])

    def perform_update(self, serializer):
        # Handle exercise data separately if needed
        exercise_data = self.request.data.get('exercise')
        if exercise_data is not None:  # Explicit None check to allow clearing exercise
            serializer.validated_data['exercise'] = exercise_data
        serializer.save()

    def perform_destroy(self, instance):
        course_id = self.kwargs['course_id']
        deleted_order = instance.order

        try:
            with transaction.atomic():
                # Delete the lesson
                instance.delete()

                # Reorder remaining lessons
                lessons = Lesson.objects.filter(
                    course_id=course_id,
                    order__gt=deleted_order
                ).order_by('order')

                for lesson in lessons:
                    lesson.order -= 1
                    lesson.save()

        except Exception as e:
            raise serializers.ValidationError(
                {'error': f'Failed to delete lesson: {str(e)}'}
            )

    def put(self, request, course_id, id):
        try:
            lesson = Lesson.objects.get(id=id, course_id=course_id)
            serializer = LessonSerializer(lesson, data=request.data)
            if serializer.is_valid():
                try:
                    serializer.save()
                    return Response(serializer.data)
                except ValidationError as e:
                    return Response({'error': e.message_dict}, status=400)
            return Response(serializer.errors, status=400)
        except Lesson.DoesNotExist:
            return Response({'error': 'Lesson not found'}, status=404)

class BulkLessonActionsView(generics.GenericAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = LessonSerializer

    def post(self, request, course_id):
        action = request.data.get('action')
        lesson_ids = request.data.get('lesson_ids', [])

        if not action or not lesson_ids:
            return Response(
                {'error': 'Action and lesson_ids are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate that the lessons belong to the course
        lessons = Lesson.objects.filter(
            course_id=course_id,
            id__in=lesson_ids
        )

        if not lessons.exists():
            return Response(
                {'error': 'No valid lessons found for this course'},
                status=status.HTTP_404_NOT_FOUND
            )

        if action == 'activate':
            lessons.update(is_active=True)
            return Response(
                {'success': f'{len(lessons)} lessons activated'},
                status=status.HTTP_200_OK
            )
        elif action == 'deactivate':
            lessons.update(is_active=False)
            return Response(
                {'success': f'{len(lessons)} lessons deactivated'},
                status=status.HTTP_200_OK
            )
        elif action == 'delete':
            # We need to handle order updates when deleting multiple lessons
            try:
                with transaction.atomic():
                    # Get all lessons to be deleted with their orders
                    to_delete = list(lessons.values('id', 'order'))

                    # Delete the lessons
                    deleted_count = lessons.count()
                    lessons.delete()

                    # Reorder remaining lessons
                    for lesson_info in to_delete:
                        Lesson.objects.filter(
                            course_id=course_id,
                            order__gt=lesson_info['order']
                        ).update(order=models.F('order') - 1)

                return Response(
                    {'success': f'{deleted_count} lessons deleted'},
                    status=status.HTTP_200_OK
                )
            except Exception as e:
                return Response(
                    {'error': f'Failed to delete lessons: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            return Response(
                {'error': 'Invalid action. Use "activate", "deactivate", or "delete"'},
                status=status.HTTP_400_BAD_REQUEST
            )

class LessonReorderView(generics.GenericAPIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, course_id):
        lesson_order = request.data.get('order', [])

        if not lesson_order:
            return Response({'error': 'Order list is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # Validate all lessons belong to the course
                existing_lessons = set(Lesson.objects.filter(
                    course_id=course_id
                ).values_list('id', flat=True))

                if set(lesson_order) != existing_lessons:
                    return Response(
                        {'error': 'Lesson IDs do not match course lessons'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Update orders
                for index, lesson_id in enumerate(lesson_order, start=1):
                    Lesson.objects.filter(id=lesson_id).update(order=index)

            return Response({'status': 'success'}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

@api_view(['POST', 'PUT'])
@permission_classes([IsAdminUser])
def manage_lesson_exercise(request, lesson_id):
    try:
        lesson = Lesson.objects.get(id=lesson_id)
    except Lesson.DoesNotExist:
        return Response({'error': 'Lesson not found'}, status=404)

    # Get ALL exercise data from request
    exercise_data = {
        'paragraph': request.data.get('paragraph'),
        'fill_blank': request.data.get('fill_blank'),
        'multiple_choice': request.data.get('multiple_choice')
    }

    # Remove None values
    exercise_data = {k: v for k, v in exercise_data.items() if v is not None}

    if not exercise_data:
        return Response({'error': 'No exercise data provided'}, status=400)

    # Save ALL exercise data
    lesson.exercise = exercise_data
    lesson.save()

    return Response({'exercise': lesson.exercise}, status=200 if request.method == 'PUT' else 201)

@api_view(['POST'])
@permission_classes([IsAdminUser])
def upload_lesson_video(request, course_id, lesson_id=None):
    """
    Handle video uploads either by file or URL with validation and cleanup on failure.
    """
    try:
        # Validate course exists
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=404)

        # Validate lesson exists if lesson_id is provided
        lesson = None
        if lesson_id:
            try:
                lesson = Lesson.objects.get(id=lesson_id, course=course)
            except Lesson.DoesNotExist:
                return Response({'error': 'Lesson not found'}, status=404)

        # Get data from request
        video_url = request.data.get('video_url', '').strip()
        video_file = request.FILES.get('video')

        if not video_url and not video_file:
            return Response({'error': 'Either video URL or video file must be provided'}, status=400)

        if video_url and video_file:
            return Response({'error': 'Cannot provide both URL and file upload'}, status=400)

        # -----------------------------
        # Handle URL case
        # -----------------------------
        if video_url:
            if not (video_url.startswith(('http://', 'https://', 'videos/')) or
                   video_url.startswith(('youtube.com', 'youtu.be', 'vimeo.com'))):
                if any(domain in video_url for domain in ['youtube', 'youtu.be', 'vimeo']):
                    video_url = f'https://{video_url}'
                else:
                    return Response(
                        {"error": "Please enter a valid video URL or upload a file"},
                        status=400
                    )

            # Convert to embed URL
            if 'youtube.com/watch' in video_url:
                video_id = video_url.split('v=')[1].split('&')[0]
                video_url = f'https://www.youtube.com/embed/{video_id}'
            elif 'youtu.be' in video_url:
                video_id = video_url.split('youtu.be/')[1].split('?')[0]
                video_url = f'https://www.youtube.com/embed/{video_id}'
            elif 'vimeo.com' in video_url and 'player.vimeo.com' not in video_url:
                video_id = video_url.split('vimeo.com/')[1].split('?')[0]
                video_url = f'https://player.vimeo.com/video/{video_id}'

            # REMOVED: Strict local path validation that was causing issues
            # Allow any valid local video path for existing lessons

            if lesson:
                # Remove old local file
                if lesson.video_url and lesson.video_url.startswith('videos/'):
                    old_video_path = os.path.join(settings.MEDIA_ROOT, lesson.video_url)
                    if os.path.exists(old_video_path):
                        try:
                            os.remove(old_video_path)
                        except OSError:
                            pass

                # Validate model before saving
                try:
                    lesson.video_url = video_url
                    lesson.full_clean()
                    lesson.save()
                except ValidationError as e:
                    return Response({'error': e.message_dict}, status=400)

            return Response({
                'video_url': video_url,
                'type': 'url',
                'message': 'Video URL saved successfully',
                'id': lesson.id if lesson else None  # Return lesson ID
            }, status=201)

        # -----------------------------
        # Handle file upload case
        # -----------------------------
        if video_file:
            valid_extensions = ['.mp4', '.webm', '.ogg']
            ext = os.path.splitext(video_file.name)[1].lower()
            if ext not in valid_extensions:
                return Response({
                    'error': f'Invalid video format. Supported formats: {", ".join(valid_extensions)}'
                }, status=400)

            max_size = 100 * 1024 * 1024  # 100MB
            if video_file.size > max_size:
                return Response({
                    'error': f'File too large. Maximum size is {max_size // (1024*1024)}MB'
                }, status=400)

            upload_dir = os.path.join('videos', f'course_{course_id}')
            if lesson_id:
                upload_dir = os.path.join(upload_dir, f'lesson_{lesson_id}')

            full_upload_path = os.path.join(settings.MEDIA_ROOT, upload_dir)
            os.makedirs(full_upload_path, exist_ok=True)

            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            clean_filename = re.sub(r'[^\w\-_\.]', '_', video_file.name)
            filename = f"{timestamp}_{clean_filename}"

            fs = FileSystemStorage(location=full_upload_path)
            saved_name = fs.save(filename, video_file)

            video_url = os.path.join(upload_dir, saved_name).replace('\\', '/')
            full_url = request.build_absolute_uri(settings.MEDIA_URL + video_url)

            if lesson:
                if lesson.video_url and lesson.video_url.startswith('videos/'):
                    old_video_path = os.path.join(settings.MEDIA_ROOT, lesson.video_url)
                    if os.path.exists(old_video_path):
                        try:
                            os.remove(old_video_path)
                        except OSError:
                            pass

                # Validate model before saving
                try:
                    lesson.video_url = video_url
                    lesson.full_clean()
                    lesson.save()
                except ValidationError as e:
                    # Cleanup if validation fails
                    fs.delete(saved_name)
                    return Response({'error': e.message_dict}, status=400)

            return Response({
                'video_url': video_url,
                'full_url': full_url,
                'filename': saved_name,
                'size': video_file.size,
                'type': 'file',
                'message': 'Video uploaded successfully',
                'id': lesson.id if lesson else None  # Return lesson ID
            }, status=201)

    except Exception as e:
        logger.error(f"Video upload failed: {str(e)}", exc_info=True)
        return Response(
            {'error': 'Failed to process video. Please try again.'},
            status=500
        )

@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def delete_lesson_video(request, course_id, lesson_id):
    """
    Delete video file for a lesson
    """
    try:
        lesson = Lesson.objects.get(id=lesson_id, course_id=course_id)

        if lesson.video_url:
            # Remove file from filesystem
            video_path = os.path.join(settings.MEDIA_ROOT, lesson.video_url)
            if os.path.exists(video_path):
                os.remove(video_path)

            # Clear video_url from lesson
            lesson.video_url = ''
            lesson.save()

            return Response({'message': 'Video deleted successfully'}, status=200)
        else:
            return Response({'error': 'No video to delete'}, status=404)

    except Lesson.DoesNotExist:
        return Response({'error': 'Lesson not found'}, status=404)
    except Exception as e:
        logger.error(f"Video deletion failed: {str(e)}")
        return Response({'error': f'Delete failed: {str(e)}'}, status=500)


# =====================
# ENROLLMENT MANAGEMENT
# =====================

class EnrollmentListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        enrollments = Enrollment.objects.select_related('student', 'course').all()

        enrollment_data = []
        for enrollment in enrollments:
            enrollment_data.append({
                'id': enrollment.id,
                'student_id': enrollment.student.id,
                'student_name': enrollment.student_name,  # Use computed property
                'student_email': enrollment.student_email,  # Use computed property
                'course_id': enrollment.course.id,
                'course_title': enrollment.course_title,  # Use computed property
                'course_code': enrollment.course_code,  # Use computed property
                'status': enrollment.status,
                'enrolled_at': enrollment.enrolled_at,
                'completed_at': enrollment.completed_at,
                'progress': enrollment.progress,  # Use computed property
                'exercises_completed': enrollment.exercises_completed,  # Use computed property
                'exercises_total': enrollment.exercises_total  # Use computed property
            })

        return Response(enrollment_data)

class EnrollmentStatisticsView(APIView):
    def get(self, request):
        # Get filter parameters
        status_filter = request.GET.get('status', '')
        course_filter = request.GET.get('course', '')
        search_query = request.GET.get('search', '')

        # Apply filters to queryset
        queryset = Enrollment.objects.all()

        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if course_filter:
            queryset = queryset.filter(course_id=course_filter)
        if search_query:
            queryset = queryset.filter(
                Q(student__first_name__icontains=search_query) |
                Q(student__last_name__icontains=search_query) |
                Q(student__email__icontains=search_query) |
                Q(course__title__icontains=search_query)
            )

        # Calculate filtered statistics
        stats = queryset.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='pending')),
            approved=Count('id', filter=Q(status='approved')),
            completed=Count('id', filter=Q(status='completed'))
        )
        return Response(stats)

class AutoApprovalSettingsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        try:
            setting = AutoApprovalSettings.objects.latest('id')
            serializer = AutoApprovalSettingsSerializer(setting)
            return Response(serializer.data)
        except AutoApprovalSettings.DoesNotExist:
            return Response({'enabled': False})

    def post(self, request):
        enabled = request.data.get('enabled', False)
        setting = AutoApprovalSettings.objects.create(
            enabled=enabled,
            updated_by=request.user
        )
        serializer = AutoApprovalSettingsSerializer(setting)
        return Response(serializer.data)

class EnrollmentActionView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk, action):
        try:
            enrollment = get_object_or_404(Enrollment, pk=pk)

            if action == 'approve':
                enrollment.status = Enrollment.APPROVED
            elif action == 'decline':
                enrollment.status = Enrollment.DECLINED
            elif action == 'complete':
                enrollment.status = Enrollment.COMPLETED
            elif action == 'reset':
                # Reset all exercises for this enrollment
                StudentExercise.objects.filter(
                    student=enrollment.student,
                    lesson__course=enrollment.course
                ).update(completed=False, completed_at=None)
                enrollment.status = Enrollment.APPROVED
                enrollment.completed_at = None
            else:
                return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)

            enrollment.save()
            serializer = EnrollmentSerializer(enrollment)
            return Response(serializer.data)

        except Enrollment.DoesNotExist:
            return Response({'error': 'Enrollment not found'}, status=status.HTTP_404_NOT_FOUND)

class EnrollmentProgressDetailView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, pk):
        try:
            enrollment = get_object_or_404(Enrollment, pk=pk)
            exercises = StudentExercise.objects.filter(
                student=enrollment.student,
                lesson__course=enrollment.course
            ).select_related('lesson')

            serializer = EnrollmentStudentExerciseSerializer(exercises, many=True)

            # Calculate overall progress
            total_exercises = Lesson.objects.filter(course=enrollment.course).count()
            completed_exercises = exercises.filter(completed=True).count()
            progress = 0
            if total_exercises > 0:
                progress = round((completed_exercises / total_exercises) * 100, 1)

            return Response({
                'student_name': enrollment.student.get_full_name(),
                'student_email': enrollment.student.email,
                'course_title': enrollment.course.title,
                'progress': progress,
                'exercises_total': total_exercises,
                'exercises_completed': completed_exercises,
                'exercises': serializer.data
            })

        except Enrollment.DoesNotExist:
            return Response({'error': 'Enrollment not found'}, status=status.HTTP_404_NOT_FOUND)

class BulkEnrollmentActionsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        action = request.data.get('action')
        enrollment_ids = request.data.get('enrollment_ids', [])

        if not action or not enrollment_ids:
            return Response(
                {'error': 'Missing action or enrollment IDs'},
                status=status.HTTP_400_BAD_REQUEST
            )

        enrollments = Enrollment.objects.filter(id__in=enrollment_ids)

        if action == 'approve':
            enrollments.update(status=Enrollment.APPROVED)
        elif action == 'decline':
            enrollments.update(status=Enrollment.DECLINED)
        elif action == 'complete':
            enrollments.update(status=Enrollment.COMPLETED)
        elif action == 'reset':
            # Reset progress for each enrollment
            for enrollment in enrollments:
                StudentExercise.objects.filter(
                    student=enrollment.student,
                    lesson__course=enrollment.course
                ).update(completed=False, completed_at=None)
                enrollment.status = Enrollment.APPROVED
                enrollment.completed_at = None
                enrollment.save()
        else:
            return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'message': f'Action "{action}" applied to {enrollments.count()} enrollments'
        })

class StudentListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        try:
            # Get students with their profiles
            students = CustomUser.objects.select_related('user_profile').filter(
                user_profile__user_type='student'
            )

            student_data = []
            for student in students:
                try:
                    student_data.append({
                        'id': student.id,
                        'first_name': student.first_name,
                        'last_name': student.last_name,
                        'email': student.email,
                        'full_name': student.get_full_name(),
                        'total_enrollments': student.enrollments.count(),
                        'completed_courses': student.enrollments.filter(status='completed').count()
                    })
                except Exception as e:
                    logger.warning(f"Error processing student {student.id}: {e}")
                    continue

            logger.info(f"Retrieved {len(student_data)} students")
            return Response(student_data)

        except Exception as e:
            logger.error(f"Error fetching students: {e}", exc_info=True)
            return Response(
                {'error': 'Failed to load students'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

#Enrollment
class EnrollmentListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        """Get all enrollments with detailed information"""
        try:
            enrollments = Enrollment.objects.select_related(
                'student', 'course', 'student__user_profile'
            ).prefetch_related(
                'student__student_exercises__lesson'
            ).all()

            # Add computed fields for serialization
            enrollment_data = []
            for enrollment in enrollments:
                enrollment_dict = {
                    'id': enrollment.id,
                    'student': enrollment.student.id,
                    'student_name': enrollment.student_name,
                    'student_email': enrollment.student_email,
                    'course': enrollment.course.id,
                    'course_title': enrollment.course_title,
                    'course_code': enrollment.course_code,
                    'status': enrollment.status,
                    'enrolled_at': enrollment.enrolled_at,
                    'completed_at': enrollment.completed_at,
                    'progress': enrollment.progress,
                    'exercises_completed': enrollment.exercises_completed,
                    'exercises_total': enrollment.exercises_total,
                    'notes': enrollment.notes
                }
                enrollment_data.append(enrollment_dict)

            return Response(enrollment_data)

        except Exception as e:
            logger.error(f"Error fetching enrollments: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Failed to fetch enrollments'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StudentListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        """Get all students for enrollment dropdown"""
        try:
            # Get all users who are students (have user_profile with user_type='student')
            students = CustomUser.objects.select_related('user_profile').filter(
                user_profile__user_type='student',
                is_active=True
            ).order_by('first_name', 'last_name')

            student_data = []
            for student in students:
                student_data.append({
                    'id': student.id,
                    'first_name': student.first_name,
                    'last_name': student.last_name,
                    'email': student.email,
                    'full_name': student.get_full_name(),
                    'total_enrollments': student.admin_enrollments.count(),
                    'completed_courses': student.admin_enrollments.filter(status='completed').count()
                })

            return Response(student_data)

        except Exception as e:
            logger.error(f"Error fetching students: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Failed to fetch students'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CourseListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        """Get all active courses for enrollment dropdown"""
        try:
            courses = Course.objects.filter(is_active=True).order_by('title')
            serializer = EnrollmentCourseSerializer(courses, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error fetching courses: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Failed to fetch courses'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EnrollmentCreateView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        """Create a new enrollment"""
        student_id = request.data.get('student')
        course_id = request.data.get('course')

        logger.info(f"Enrollment creation attempt: student_id={student_id}, course_id={course_id}")

        # Validate required fields
        if not student_id or not course_id:
            return Response(
                {'error': 'Both student and course are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Convert to integers if they're strings
        try:
            student_id = int(student_id)
            course_id = int(course_id)
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid ID format: {e}")
            return Response(
                {'error': 'Invalid student or course ID format'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use atomic transaction to prevent race conditions
        try:
            with transaction.atomic():
                # Validate student exists and has correct user type
                try:
                    student = CustomUser.objects.select_related('user_profile').get(id=student_id)

                    # Check if user has a profile and is a student
                    if not hasattr(student, 'user_profile'):
                        logger.error(f"Student {student_id} has no user profile")
                        return Response(
                            {'error': 'Selected user has no profile'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    if student.user_profile.user_type != 'student':
                        logger.error(f"User {student_id} is not a student: {student.user_profile.user_type}")
                        return Response(
                            {'error': 'Selected user is not a student'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                except CustomUser.DoesNotExist:
                    logger.error(f"Student {student_id} does not exist")
                    return Response(
                        {'error': 'Student does not exist'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Validate course exists and is active
                try:
                    course = Course.objects.get(id=course_id)
                    if not course.is_active:
                        logger.error(f"Course {course_id} is not active")
                        return Response(
                            {'error': 'Course is not active'},
                            status=status.HTTP_400_BAD_REQUEST
                        )
                except Course.DoesNotExist:
                    logger.error(f"Course {course_id} does not exist")
                    return Response(
                        {'error': f'Course with ID {course_id} does not exist. Please refresh the page and try again.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Check for duplicate enrollment
                existing_enrollment = Enrollment.objects.filter(
                    student_id=student_id,
                    course_id=course_id
                ).first()

                if existing_enrollment:
                    logger.warning(f"Duplicate enrollment attempt: student {student_id}, course {course_id}")
                    return Response(
                        {'error': 'Student is already enrolled in this course'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                # Create the enrollment
                enrollment_data = {
                    'student_id': student_id,
                    'course_id': course_id,
                    'status': request.data.get('status', 'pending'),
                    'notes': request.data.get('notes', '')
                }

                enrollment = Enrollment.objects.create(**enrollment_data)
                logger.info(f"Enrollment created successfully: ID {enrollment.id}")

                return Response({
                    'id': enrollment.id,
                    'student': enrollment.student.id,
                    'student_name': student.get_full_name(),
                    'student_email': student.email,
                    'course': enrollment.course.id,
                    'course_title': course.title,
                    'course_code': course.code,
                    'status': enrollment.status,
                    'message': 'Student enrolled successfully!'
                }, status=status.HTTP_201_CREATED)

        except IntegrityError as e:
            logger.error(f"Database integrity error: {e}")
            lower = str(e).lower()
            if 'unique' in lower:
                return Response(
                    {'error': 'Student is already enrolled in this course'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if 'foreign key' in lower:
                return Response(
                    {'error': 'Invalid student or course reference. Please refresh the page and try again.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            return Response(
                {'error': 'Database constraint violation'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except ValidationError as e:
            logger.error(f"Validation error: {e}")
            return Response(
                {'error': f'Validation error: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Unexpected error in enrollment creation: {str(e)}", exc_info=True)
            return Response(
                {'error': 'An unexpected error occurred. Please contact support.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EnrollmentActionView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk, action):
        """Handle enrollment actions: approve, decline, complete, reset"""
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
                # Reset all student exercises for this course
                StudentExercise.objects.filter(
                    student=enrollment.student,
                    lesson__course=enrollment.course
                ).update(completed=False, completed_at=None, score=0.0)

                enrollment.status = Enrollment.APPROVED
                enrollment.completed_at = None
                enrollment.save()
                message = 'Progress reset successfully'

            else:
                return Response(
                    {'error': 'Invalid action'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return Response({'message': message})

        except Exception as e:
            logger.error(f"Error performing action {action} on enrollment {pk}: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Failed to {action} enrollment'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class EnrollmentProgressDetailView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, pk):
        """Get detailed progress information for an enrollment"""
        try:
            enrollment = get_object_or_404(
                Enrollment.objects.select_related('student', 'course'),
                pk=pk
            )

            # Get all exercises for this course
            exercises = StudentExercise.objects.filter(
                student=enrollment.student,
                lesson__course=enrollment.course
            ).select_related('lesson').order_by('lesson__order')

            exercise_data = []
            for exercise in exercises:
                exercise_data.append({
                    'id': exercise.id,
                    'title': exercise.lesson.title,
                    'description': exercise.lesson.description or '',
                    'completed': exercise.completed,
                    'completed_at': exercise.completed_at,
                    'score': exercise.score
                })

            return Response({
                'id': enrollment.id,
                'student_name': enrollment.student_name,
                'student_email': enrollment.student_email,
                'course_title': enrollment.course_title,
                'progress': enrollment.progress,
                'exercises': exercise_data
            })

        except Exception as e:
            logger.error(f"Error fetching enrollment details for {pk}: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Failed to load enrollment details'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BulkEnrollmentActionsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        """Handle bulk actions on multiple enrollments"""
        action = request.data.get('action')
        enrollment_ids = request.data.get('enrollment_ids', [])

        if not action or not enrollment_ids:
            return Response(
                {'error': 'Action and enrollment IDs are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

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
                    # Reset exercises for all enrollments
                    for enrollment in enrollments:
                        StudentExercise.objects.filter(
                            student=enrollment.student,
                            lesson__course=enrollment.course
                        ).update(completed=False, completed_at=None, score=0.0)

                    enrollments.update(status=Enrollment.APPROVED, completed_at=None)
                else:
                    return Response(
                        {'error': 'Invalid action'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                return Response({'message': f'Bulk action {action} completed successfully'})

        except Exception as e:
            logger.error(f"Error performing bulk action {action}: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Bulk action failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AutoApprovalSettingsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        """Get auto-approval settings"""
        settings, created = AutoApprovalSettings.objects.get_or_create(defaults={'enabled': False})
        return Response({'enabled': settings.enabled})

    def post(self, request):
        """Update auto-approval settings"""
        enabled = request.data.get('enabled', False)
        settings, created = AutoApprovalSettings.objects.get_or_create(defaults={'enabled': False})
        settings.enabled = enabled
        settings.updated_by = request.user
        settings.save()
        return Response({'enabled': settings.enabled})


class EnrollmentStatisticsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        """Get enrollment statistics"""
        try:
            total_enrollments = Enrollment.objects.count()
            pending_enrollments = Enrollment.objects.filter(status=Enrollment.PENDING).count()
            approved_enrollments = Enrollment.objects.filter(status=Enrollment.APPROVED).count()
            completed_enrollments = Enrollment.objects.filter(status=Enrollment.COMPLETED).count()
            declined_enrollments = Enrollment.objects.filter(status=Enrollment.DECLINED).count()

            return Response({
                'total': total_enrollments,
                'pending': pending_enrollments,
                'approved': approved_enrollments,
                'completed': completed_enrollments,
                'declined': declined_enrollments
            })

        except Exception as e:
            logger.error(f"Error fetching enrollment statistics: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Failed to fetch statistics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# Revenue
class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.select_related(
        'course', 'student__user', 'teacher__user'
    ).all()
    serializer_class = TransactionSerializer
    permission_classes = [IsAdminUser]
    ordering = ['-created_at']  # Add default ordering

    def list(self, request, *args, **kwargs):
        # Add debug logging
        queryset = self.get_queryset()

        # Apply ordering
        ordering = request.query_params.get('ordering', '-created_at')
        queryset = queryset.order_by(ordering)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class TeacherPayoutViewSet(viewsets.ModelViewSet):
    queryset = TeacherPayout.objects.select_related('teacher__user').all()
    serializer_class = TeacherPayoutSerializer
    permission_classes = [IsAdminUser]

    @action(detail=True, methods=['post'])
    def process_payout(self, request, pk=None):
        payout = self.get_object()

        if payout.status != 'pending':
            return Response(
                {'error': 'Only pending payouts can be processed'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Implement payout processing logic here
        payout.status = 'processed'
        payout.processed_at = timezone.now()
        payout.save()

        return Response({'status': 'payout processed'})

class RevenueReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RevenueReport.objects.all()
    serializer_class = RevenueReportSerializer
    permission_classes = [IsAdminUser]

    @action(detail=False, methods=['get'])
    def summary(self, request):
        # Get summary statistics for dashboard
        total_revenue = Transaction.objects.filter(
            status='completed'
        ).aggregate(total=Sum('amount'))['total'] or 0

        platform_commission = Transaction.objects.filter(
            status='completed'
        ).aggregate(total=Sum('platform_fee'))['total'] or 0

        teacher_payouts = Transaction.objects.filter(
            status='completed', teacher__isnull=False
        ).aggregate(total=Sum('teacher_payout'))['total'] or 0

        # Count active teachers (those with courses and sales)
        active_teachers = UserProfile.objects.filter(
            user_type='teacher',
            courses_taught__isnull=False,
            sales__isnull=False
        ).distinct().count()

        hosting_fees = active_teachers * 200  # R200 per teacher

        return Response({
            'total_revenue': total_revenue,
            'platform_commission': platform_commission,
            'teacher_payouts': teacher_payouts,
            'hosting_fees': hosting_fees,
            'active_teachers': active_teachers
        })

# PayPal integration views
class CreatePaymentView(APIView):
    """Create a PayPal payment for testing - Class Based View"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        from .paypal_utils import create_paypal_order
        from .models import Course, UserProfile, Transaction

        try:
            data = request.data
            course_id = data.get('course_id')
            student_id = data.get('student_id')
            country_code = data.get('country_code', 'US')

            # Get course and student
            course = Course.objects.get(id=course_id)
            student = UserProfile.objects.get(id=student_id, user_type='student')

            # Determine currency based on country code
            currency = 'ZAR' if country_code == 'ZA' else 'USD'

            # Create transaction record first
            transaction = Transaction.objects.create(
                course=course,
                student=student,
                teacher=course.teacher,
                amount=course.price,
                currency=currency,
                status='pending'
            )

            # Create PayPal order (sandbox mode)
            order = create_paypal_order(
                amount=course.price,
                currency=currency,
                course_name=course.title,
                transaction_id=transaction.transaction_id
            )

            # Update transaction with PayPal order ID
            transaction.paypal_order_id = order['id']
            transaction.save()

            return Response({
                'orderID': order['id'],
                'transactionID': transaction.transaction_id
            })

        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        except UserProfile.DoesNotExist:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CapturePaymentView(APIView):
    """Capture a PayPal payment for testing - Class Based View"""
    permission_classes = [IsAdminUser]

    def post(self, request):
        from .paypal_utils import capture_paypal_order
        from .models import Transaction

        try:
            data = request.data
            order_id = data.get('orderID')

            # Capture payment with PayPal
            capture_data = capture_paypal_order(order_id)

            # Find and update transaction
            transaction = Transaction.objects.get(paypal_order_id=order_id)

            if capture_data['status'] == 'COMPLETED':
                # Get capture amount
                capture_amount = Decimal(capture_data['purchase_units'][0]['payments']['captures'][0]['amount']['value'])

                # Apply revenue split logic
                if transaction.teacher:  # Teacher course
                    transaction.platform_fee = capture_amount * Decimal('0.3')
                    transaction.teacher_payout = capture_amount * Decimal('0.7')

                    # Apply hosting fee if not first month
                    teacher_profile = transaction.teacher
                    if not teacher_profile.is_first_month:
                        transaction.teacher_payout -= Decimal('200.00')
                        transaction.hosting_fee_applied = True
                else:  # Admin course
                    transaction.platform_fee = capture_amount
                    transaction.teacher_payout = Decimal('0.00')

                transaction.status = 'completed'
                transaction.gateway_transaction_id = capture_data['purchase_units'][0]['payments']['captures'][0]['id']
                transaction.save()

                return Response({
                    'status': 'success',
                    'transactionID': transaction.transaction_id,
                    'platform_fee': transaction.platform_fee,
                    'teacher_payout': transaction.teacher_payout
                })
            else:
                transaction.status = 'failed'
                transaction.save()
                return Response({'status': 'failed'}, status=status.HTTP_400_BAD_REQUEST)

        except Transaction.DoesNotExist:
            return Response({'error': 'Transaction not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def generate_test_transactions(request):
    """
    Generate test transaction data for development and testing
    """
    from .models import Transaction, Course, UserProfile

    try:
        # Get or create test users
        student, _ = UserProfile.objects.get_or_create(
            user_type='student',
            defaults={'user_id': 1}  # You might need to adjust this
        )

        teacher, _ = UserProfile.objects.get_or_create(
            user_type='teacher',
            defaults={'user_id': 2}
        )

        # Get a course or create a test one
        course, _ = Course.objects.get_or_create(
            title='Test Course',
            defaults={
                'price': Decimal('100.00'),
                'teacher': teacher
            }
        )

        # Number of transactions to generate
        count = request.data.get('count', 10)

        transactions_created = []

        for i in range(count):
            # Randomize values for variety
            amount = Decimal(random.randint(50, 500))
            days_ago = random.randint(0, 30)
            status = random.choice(['completed', 'completed', 'completed', 'pending', 'refunded'])
            currency = random.choice(['USD', 'ZAR'])

            # Create transaction
            transaction = Transaction.objects.create(
                course=course,
                student=student,
                teacher=course.teacher,
                amount=amount,
                currency=currency,
                status=status,
                created_at=timezone.now() - timedelta(days=days_ago)
            )

            # For completed transactions, simulate PayPal data
            if status == 'completed':
                transaction.paypal_order_id = f"PAYPAL-TEST-{transaction.id}"
                transaction.gateway_transaction_id = f"GATEWAY-{transaction.id}"
                transaction.save()

            transactions_created.append({
                'id': transaction.id,
                'transaction_id': transaction.transaction_id,
                'amount': str(transaction.amount),
                'currency': transaction.currency,
                'status': transaction.status,
                'platform_fee': str(transaction.platform_fee),
                'teacher_payout': str(transaction.teacher_payout)
            })

        return Response({
            'message': f'Successfully created {count} test transactions',
            'transactions': transactions_created
        })

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def clear_test_transactions(request):
    """
    Clear all transactions (use with caution!)
    """
    from .models import Transaction

    try:
        count, _ = Transaction.objects.all().delete()
        return Response({'message': f'Deleted {count} transactions'})

    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class DashboardStatisticsView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        try:
            # Get total registered users
            total_users = CustomUser.objects.count()

            # Get active courses count
            active_courses = Course.objects.filter(is_active=True).count()

            # Get total enrollments count
            total_enrollments = Enrollment.objects.count()

            # Monthly revenue - set to 0 as requested
            monthly_revenue = 0

            return Response({
                'total_users': total_users,
                'active_courses': active_courses,
                'total_enrollments': total_enrollments,
                'monthly_revenue': monthly_revenue
            })

        except Exception as e:
            logger.error(f"Error fetching dashboard statistics: {str(e)}")
            return Response(
                {'error': 'Failed to fetch dashboard statistics'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )