# student_dashboard/views.py
from rest_framework import generics, permissions, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from accounts.models import Course, CustomUser, UserProfile
from admin_dashboard.models import Lesson, Enrollment, LessonProgress, VideoAnalytics
from django.db.models import Count, Q, F
from rest_framework.serializers import ModelSerializer
from .serializers import (CourseListSerializer, LessonSerializer, CourseDetailSerializer,
 LessonListSerializer, LessonDetailSerializer, GuestSessionSerializer, GuestCourseSerializer,
 GuestLessonSerializer,  CertificateSerializer, CommentSerializer, CommentCreateSerializer,
 ReplyCreateSerializer, ReplySerializer
)
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from datetime import timedelta
import logging
import json
from rest_framework import generics, permissions
from rest_framework.response import Response
from accounts.models import Course
from admin_dashboard.models import Lesson, Enrollment, LessonProgress
from django.db.models import Count, Q
from rest_framework.serializers import ModelSerializer
from rest_framework import serializers
from .models import (
 StudentExercise, GuestSession, GuestAccessSettings, Certificate,
 CommentReaction, Reply, Comment, ReplyReaction
)
from django.utils.text import slugify as django_slugify
from rest_framework.views import APIView
import re
import ast
import uuid

logger = logging.getLogger(__name__)
# student_dashboard/views.py - REPLACE StudentCourseListView

# student_dashboard/views.py - REPLACE StudentCourseListView

class StudentCourseListView(generics.ListAPIView):
    """
    ✅ FIXED: Return ALL courses with enrollment status
    Enrolled courses are sorted first
    """
    serializer_class = CourseListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # ✅ Return ALL active courses (not just enrolled ones)
        return Course.objects.filter(is_active=True).order_by('title')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        user = request.user

        # Serialize all courses
        all_courses_data = []

        for course in queryset:
            # Get enrollment status
            enrollment = Enrollment.objects.filter(student=user, course=course).first()
            enrollment_status = enrollment.status if enrollment else 'not_enrolled'
            is_enrolled = enrollment_status in ['approved', 'completed', 'enrolled']

            # Get lessons count
            lessons_count = Lesson.objects.filter(course=course, is_active=True).count()

            # ✅ Count videos
            video_count = Lesson.objects.filter(
                course=course,
                is_active=True
            ).exclude(
                Q(video_url__isnull=True) |
                Q(video_url='') |
                Q(video_url='null')
            ).count()

            # ✅ Count exercises (lessons with exercises)
            exercises_count = 0
            lessons = Lesson.objects.filter(course=course, is_active=True)
            for lesson in lessons:
                if lesson.exercise:
                    exercises_count += 1

            # Calculate progress for enrolled courses
            progress = 0
            if is_enrolled and lessons_count > 0:
                from student_dashboard.models import StudentExercise
                completed_lessons = StudentExercise.objects.filter(
                    student=user,
                    lesson__course=course,
                    completed=True
                ).count()
                progress = round((completed_lessons / lessons_count) * 100, 1)

            # Build course data
            course_data = {
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'description': course.description,
                'price': float(course.price) if course.price else 0.0,
                'is_active': course.is_active,
                'progress': progress,
                'completed_lessons': StudentExercise.objects.filter(
                    student=user,
                    lesson__course=course,
                    completed=True
                ).count() if is_enrolled else 0,
                'total_lessons': lessons_count,
                'enrollment_status': enrollment_status,
                'is_enrolled': is_enrolled,
                'total_exercises': exercises_count,
                'video_count': video_count,  # ✅ INCLUDE VIDEO COUNT
                'category': course.get_category_display(),
                'is_popular': course.is_popular,
                'is_new': course.is_new,
                'duration': course.duration,
                'teacher_name': course.teacher_name,
                'created_at': course.created_at.isoformat() if course.created_at else None,
            }

            all_courses_data.append(course_data)

        # ✅ SORT: Enrolled courses first, then others
        all_courses_data.sort(key=lambda x: (not x['is_enrolled'], x['title']))

        # Calculate statistics
        total_enrollments = Enrollment.objects.filter(student=user).count()
        enrolled_count = sum(1 for c in all_courses_data if c['is_enrolled'])
        completed_courses = sum(1 for c in all_courses_data if c['progress'] == 100)

        return Response({
            'courses': all_courses_data,
            'statistics': {
                'total_courses': len(all_courses_data),
                'total_enrollments': total_enrollments,
                'enrolled_courses': enrolled_count,
                'completed_courses': completed_courses,
                'active_courses': enrolled_count - completed_courses
            }
        })

class StudentCourseDetailView(generics.RetrieveAPIView):
    """
    API endpoint for students to view individual course details
    """
    serializer_class = CourseDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'code'
    lookup_url_kwarg = 'course_code'

    def get_queryset(self):
        return Course.objects.filter(is_active=True)

    def retrieve(self, request, *args, **kwargs):
        course = self.get_object()
        serializer = self.get_serializer(course)

        # Add enrollment information for this user
        user = request.user
        enrollment = Enrollment.objects.filter(student=user, course=course).first()

        # ✅ NEW: Calculate total exercises for the course
        total_exercises = self.calculate_total_exercises(course)

        course_data = serializer.data
        course_data['enrollment_status'] = enrollment.status if enrollment else 'not_enrolled'
        course_data['enrolled_at'] = enrollment.enrolled_at if enrollment else None
        course_data['total_exercises'] = total_exercises  # ✅ ADD THIS

        return Response(course_data)

    def calculate_total_exercises(self, course):
        """
        Calculate total exercises in the course
        Each lesson with exercise = 1 exercise
        """
        try:
            lessons = Lesson.objects.filter(course=course, is_active=True)
            total_exercises = 0

            for lesson in lessons:
                if lesson.exercise:
                    total_exercises += 1

            return total_exercises
        except Exception as e:
            print(f"Error calculating total exercises for course {course.code}: {e}")
            return 0

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def enroll_in_course(request, course_code):
    """
    API endpoint for students to enroll in a course
    """
    course = get_object_or_404(Course, code=course_code, is_active=True)
    user = request.user

    # Check if already enrolled
    existing_enrollment = Enrollment.objects.filter(student=user, course=course).first()
    if existing_enrollment:
        return Response(
            {'detail': f'You are already enrolled in this course with status: {existing_enrollment.status}'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Create new enrollment
    enrollment = Enrollment.objects.create(
        student=user,
        course=course,
        status='pending'  # Default status, can be auto-approved based on settings
    )

    return Response({
        'detail': 'Successfully enrolled in the course. Your enrollment is pending approval.',
        'enrollment_status': enrollment.status,
        'enrolled_at': enrollment.enrolled_at
    }, status=status.HTTP_201_CREATED)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_lessons_list(request):
    user = request.user

    enrolled_courses = Course.objects.filter(
        admin_enrollments__student=user,
        admin_enrollments__status__in=['approved', 'completed'],
        is_active=True
    ).distinct()

    lessons = Lesson.objects.filter(
        course__in=enrolled_courses,
        is_active=True
    ).select_related('course').prefetch_related('exercises')

    completed_lessons = StudentExercise.objects.filter(
        student=user,
        completed=True
    ).values_list('lesson_id', flat=True)

    lesson_data = []
    for lesson in lessons:
        lesson_data.append({
            'id': lesson.id,
            'title': lesson.title,
            'description': lesson.description,
            'preview': (
                lesson.description[:100] + '...'
                if lesson.description and len(lesson.description) > 100
                else lesson.description
            ),
            'course': lesson.course.title,
            'course_code': lesson.course.code,
            'order': lesson.order,
            'duration': lesson.duration,
            'created_at': lesson.created_at,
            'completed': lesson.id in completed_lessons,
            'exercise_count': lesson.exercises.count()
        })

    return Response({
        'lessons': lesson_data,
        'total_lessons': len(lesson_data),
        'completed_lessons': sum(1 for l in lesson_data if l['completed']),
        'enrolled_courses': enrolled_courses.count()
    })

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_lesson_detail_by_slug(request, course_slug, lesson_slug):
    """
    ✅ NEW: Get lesson detail for authenticated students using slugs
    """
    print(f"=== STUDENT LESSON DETAIL BY SLUG ===")
    print(f"Course Slug: {course_slug}")
    print(f"Lesson Slug: {lesson_slug}")
    print(f"User: {request.user.email}")

    if not request.user.is_authenticated:
        return Response(
            {'detail': 'Authentication required.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    try:
        # Get the course
        course = get_object_or_404(Course, code=course_slug, is_active=True)
        print(f"✅ Course found: {course.title}")

        # Get lesson by slug
        lesson = get_lesson_by_slug(course, lesson_slug)
        if not lesson:
            print(f"❌ Lesson not found by slug: {lesson_slug}")
            return Response(
                {'detail': 'Lesson not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        print(f"✅ Lesson found: {lesson.title} (ID: {lesson.id})")

        # Check enrollment
        is_enrolled = Enrollment.objects.filter(
            student=request.user,
            course=lesson.course,
            status__in=['approved', 'completed', 'enrolled']
        ).exists()

        print(f"User enrolled: {is_enrolled}")

        if not is_enrolled:
            return Response({
                'detail': 'You are not enrolled in this course.',
                'course_code': lesson.course.code,
                'course_title': lesson.course.title,
                'enrollment_required': True
            }, status=status.HTTP_403_FORBIDDEN)

        # Get student exercise record
        student_exercise = StudentExercise.objects.filter(
            student=request.user,
            lesson=lesson
        ).first()

        # Get video progress
        from admin_dashboard.models import LessonProgress
        video_progress = LessonProgress.objects.filter(
            student=request.user,
            lesson=lesson
        ).first()

        # Parse exercises from lesson.exercise field
        exercises = []
        if lesson.exercise:
            try:
                exercises = parse_exercises_from_lesson(lesson.exercise)
                print(f"Parsed {len(exercises)} exercises")
            except Exception as e:
                print(f"Error parsing exercises for lesson {lesson.id}: {e}")
                exercises = []

        # Check completion status
        completed = False
        video_completed = False

        if student_exercise:
            completed = student_exercise.completed
            print(f"Student exercise found: completed={completed}, score={student_exercise.score}")

        if video_progress:
            video_completed = video_progress.video_completed
            print(f"Video progress: completed={video_completed}")

        # Build lesson data
        lesson_data = {
            'id': lesson.id,
            'title': lesson.title,
            'description': lesson.description or '',
            'content': lesson.content or '',
            'video_url': lesson.video_url,
            'duration': lesson.duration or 30,
            'order': lesson.order or 0,

            # Course info
            'course_id': lesson.course.id,
            'course_title': lesson.course.title,
            'course_code': lesson.course.code,

            # Exercises
            'exercises': exercises,
            'exercise_count': len(exercises),

            # Completion status
            'completed': completed,
            'video_completed': video_completed,

            # Student progress
            'student_progress': {
                'exercise_score': float(student_exercise.score) if student_exercise and student_exercise.score else 0.0,
                'completed_at': student_exercise.completed_at.isoformat() if student_exercise and student_exercise.completed_at else None,
                'video_progress': video_progress.video_progress if video_progress else 0,
                'video_completed': video_completed,
            },

            # Access info
            'access_info': {
                'is_guest': False,
                'user_authenticated': True,
                'has_full_access': True,
                'can_complete_lesson': True,
                'can_save_progress': True,
                'user_type': request.user.profile.user_type if hasattr(request.user, 'profile') else 'student',
                'enrollment_status': 'approved'
            },
        }

        print(f"✅ Returning student lesson detail by slug for user {request.user.id}")
        return Response(lesson_data, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"❌ Error in student_lesson_detail_by_slug: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response(
            {'detail': f'Failed to load lesson: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

class StudentLessonDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, course_slug, lesson_slug):  # Changed to accept both slugs
        # Get course first
        course = get_object_or_404(
            Course,
            code=course_slug,
            is_active=True
        )

        # Get lesson by slug
        lesson = get_lesson_by_slug(course, lesson_slug)
        if not lesson:
            return Response(
                {"detail": "Lesson not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check enrollment
        enrolled = Enrollment.objects.filter(
            student=request.user,
            course=course,
            status__in=["approved", "completed"]
        ).exists()

        if not enrolled:
            return Response(
                {"detail": "Not enrolled in this course"},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = LessonDetailSerializer(
            lesson,
            context={"request": request}
        )

        return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_lesson_completed(request, lesson_id):
    """
    FIXED: Returns fresh lesson data for real-time sidebar updates
    """
    user = request.user


    try:
        lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)

        # Check enrollment
        enrollment = Enrollment.objects.filter(
            student=user,
            course=lesson.course,
            status__in=['approved', 'completed']
        ).first()

        if not enrollment:
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get or create student exercise
        student_exercise, created = StudentExercise.objects.get_or_create(
            student=user,
            lesson=lesson,
            defaults={
                'completed': False,
                'score': 0.0,
                'submission_data': {}
            }
        )

        # Check requirements
        completion_check = check_lesson_requirements(lesson, user)

        if not completion_check['can_complete']:
            return Response(
                {
                    'detail': 'Cannot complete lesson. Requirements not met.',
                    'missing_requirements': completion_check['missing'],
                    'completion_status': completion_check
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get completion data
        reflection = request.data.get('reflection', '').strip()
        score = float(request.data.get('score', 0))
        total_questions = int(request.data.get('total_questions', 0))

        # Mark as completed
        if not student_exercise.completed:
            student_exercise.completed = True
            student_exercise.completed_at = timezone.now()
            student_exercise.score = score if score > 0 else 1.0

            if not student_exercise.submission_data:
                student_exercise.submission_data = {}

            student_exercise.submission_data.update({
                'reflection': reflection,
                'completion_timestamp': timezone.now().isoformat(),
                'total_questions': total_questions,
                'completion_method': 'system_tracked',
                'requirements_met': completion_check['requirements_met']
            })

            student_exercise.save()

            # Force database commit
            from django.db import transaction
            transaction.commit()

            # Refresh from database
            student_exercise.refresh_from_db()

        all_lessons = Lesson.objects.filter(
            course=lesson.course,
            is_active=True
        ).select_related('course').order_by('order')

        # Query completed lesson IDs
        completed_lesson_ids = set(
            StudentExercise.objects.filter(
                student=user,
                lesson__course=lesson.course,
                completed=True
            ).values_list('lesson_id', flat=True)
        )

        # Build fresh lessons array
        lessons_data = []
        for lesson_item in all_lessons:
            is_completed = lesson_item.id in completed_lesson_ids

            lesson_data = {
                'id': lesson_item.id,
                'title': lesson_item.title,
                'description': lesson_item.description,
                'duration': lesson_item.duration,
                'order': lesson_item.order,
                'completed': is_completed,
                'created_at': lesson_item.created_at.isoformat() if lesson_item.created_at else None
            }

            lessons_data.append(lesson_data)

        # Calculate progress
        total_lessons = len(lessons_data)
        completed_lessons = len(completed_lesson_ids)
        progress_percentage = round((completed_lessons / total_lessons) * 100, 1) if total_lessons > 0 else 0

        # Build response with FRESH data
        response_data = {
            'detail': 'Lesson completed successfully!',
            'completed': True,
            'completed_at': student_exercise.completed_at.isoformat(),
            'score': student_exercise.score,
            'total_questions': total_questions,

            # ✅ CRITICAL: Fresh lessons for sidebar
            'updated_lessons': lessons_data,

            'course_progress': progress_percentage,
            'total_lessons': total_lessons,
            'completed_lessons': completed_lessons,
            'sidebar_update': True,
            'timestamp': timezone.now().isoformat()
        }

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        import traceback
        traceback.print_exc()

        return Response(
            {'detail': f'Error completing lesson: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_courses_with_exercises(request):
    """
    ✅ FIXED: Counts lessons with exercises, not individual questions
    Each lesson = 1 exercise (regardless of question count)
    """
    user = request.user

    try:
        # Get courses where the user is enrolled with approved status
        enrolled_courses = Course.objects.filter(
            admin_enrollments__student=user,
            admin_enrollments__status__in=['approved', 'completed'],
            is_active=True
        ).distinct().order_by('title')

        course_data = []
        total_exercises = 0  # Total lessons with exercises
        total_lessons = 0
        completed_courses_count = 0

        for course in enrolled_courses:
            # Get lessons for this course
            lessons = Lesson.objects.filter(course=course, is_active=True)
            lessons_count = lessons.count()
            total_lessons += lessons_count

            # ✅ FIXED: Count LESSONS with exercises, not individual questions
            # Each lesson with an exercise = 1 exercise
            exercises_count = 0
            for lesson in lessons:
                if lesson.exercise:
                    # This lesson HAS an exercise (regardless of how many questions)
                    exercises_count += 1

            total_exercises += exercises_count

            # Calculate progress based on completed lessons
            if lessons_count == 0:
                progress = 0
            else:
                completed_lessons = StudentExercise.objects.filter(
                    student=user,
                    lesson__course=course,
                    completed=True
                ).count()
                progress = round((completed_lessons / lessons_count) * 100, 1)

            # Track completed courses
            if progress == 100:
                completed_courses_count += 1

            # Build course data
            course_data.append({
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'description': course.description,
                'progress': progress,
                'total_lessons': lessons_count,
                'total_exercises': exercises_count,  # Count of lessons with exercises
                'enrollment_status': 'approved'
            })

        # Return comprehensive statistics
        return Response({
            'courses': course_data,
            'total_courses': len(course_data),
            'completed_courses': completed_courses_count,
            'total_lessons': total_lessons,
            'total_exercises': total_exercises
        })

    except Exception as e:
        print(f"❌ Error in student_courses_with_exercises: {e}")
        import traceback
        traceback.print_exc()

        return Response({
            'detail': f'Error fetching course data: {str(e)}',
            'courses': [],
            'total_courses': 0,
            'completed_courses': 0,
            'total_lessons': 0,
            'total_exercises': 0
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def course_lessons_list(request, course_code):
    """
    ✅ FIXED: API endpoint to get all lessons with video info
    """
    user = request.user

    # Get the course
    course = get_object_or_404(Course, code=course_code, is_active=True)

    # Check if user is enrolled
    enrollment = Enrollment.objects.filter(
        student=user,
        course=course,
        status__in=['approved', 'completed']
    ).first()

    if not enrollment:
        return Response(
            {'detail': 'You are not enrolled in this course.'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Get all lessons for this course
    lessons = Lesson.objects.filter(
        course=course,
        is_active=True
    ).order_by('order')

    # ✅ CRITICAL: Log video data for debugging
    print(f"\n📖 FETCHING LESSONS FOR {course_code}:")
    for lesson in lessons:
        has_video = bool(lesson.video_url and
                        lesson.video_url.strip() and
                        lesson.video_url != 'null')
        print(f"   {lesson.title}:")
        print(f"      - video_url: '{lesson.video_url}'")
        print(f"      - has_video: {has_video}")

    # Serialize lessons
    serializer = LessonListSerializer(lessons, many=True, context={'request': request})

    # Calculate progress
    total_lessons = lessons.count()
    completed_lessons = StudentExercise.objects.filter(
        student=user,
        lesson__course=course,
        completed=True
    ).count()

    progress = round((completed_lessons / total_lessons) * 100, 1) if total_lessons > 0 else 0

    # ✅ Count videos
    video_count = sum(1 for lesson in lessons if lesson.video_url and
                     lesson.video_url.strip() and
                     lesson.video_url != 'null')

    print(f"\n✅ RESPONSE SUMMARY:")
    print(f"   Total Lessons: {total_lessons}")
    print(f"   Lessons with Videos: {video_count}")
    print(f"   Completed: {completed_lessons}")

    return Response({
        'course': {
            'id': course.id,
            'title': course.title,
            'code': course.code,
            'description': course.description,
            'category': course.get_category_display(),
            'teacher_name': course.teacher.user.get_full_name() if course.teacher and course.teacher.user else None,
        },
        'lessons': serializer.data,
        'progress': {
            'total_lessons': total_lessons,
            'completed_lessons': completed_lessons,
            'percentage': progress,
            'video_count': video_count  # ✅ ADD THIS
        }
    })

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_lesson_detail(request, lesson_id):
    """
    Simplified lesson detail view for debugging
    """
    try:
        # print(f"=== VIEW DEBUG: Getting lesson {lesson_id} ===")
        user = request.user

        # Get the lesson
        lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)
        # print(f"Found lesson: {lesson.title}")

        # Check enrollment
        enrollment = Enrollment.objects.filter(
            student=user,
            course=lesson.course,
            status__in=['approved', 'completed']
        ).first()

        if not enrollment:
            # print("User not enrolled")
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # print("User is enrolled, serializing...")

        # Serialize the lesson
        serializer = LessonDetailSerializer(lesson, context={'request': request})
        lesson_data = serializer.data

        # print(f"Serialization complete. Exercises: {lesson_data.get('exercises', [])}")

        # Simple response without navigation for now
        return Response({
            'id': lesson_data['id'],
            'title': lesson_data['title'],
            'description': lesson_data['description'],
            'content': lesson_data['content'],
            'video_url': lesson_data.get('video_url'),
            'exercises': lesson_data.get('exercises', []),
            'completed': lesson_data.get('completed', False),
            'course_title': lesson_data.get('course_title'),
            'course_code': lesson_data.get('course_code'),
            'teacher': lesson_data.get('teacher')
        })

    except Exception as e:
        # print(f"VIEW ERROR: {e}")
        import traceback
        traceback.print_exc()
        return Response(
            {'detail': f'Server error: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def submit_exercise_answer(request, lesson_id, exercise_id):
    """
    ✅ FIXED: Properly accumulates score for each correct answer
    """
    user = request.user

    try:
        lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)

        enrollment = Enrollment.objects.filter(
            student=user,
            course=lesson.course,
            status__in=['approved', 'completed']
        ).first()

        if not enrollment:
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )

        student_exercise, created = StudentExercise.objects.get_or_create(
            student=user,
            lesson=lesson,
            defaults={'completed': False, 'score': 0.0, 'submission_data': {}}
        )

        submitted_answer = request.data.get('answer')
        if submitted_answer is None:
            return Response(
                {'detail': 'Answer is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Parse questions from lesson
        questions = []
        if lesson.exercise:
            try:
                if isinstance(lesson.exercise, list):
                    questions = lesson.exercise
                elif isinstance(lesson.exercise, dict):
                    if 'questions' in lesson.exercise:
                        questions = lesson.exercise['questions']
                    else:
                        question_index = 1
                        for exercise_type in ['multiple_choice', 'fill_blank', 'paragraph', 'true_false']:
                            if exercise_type in lesson.exercise:
                                ex_data = lesson.exercise[exercise_type].copy()
                                ex_data['type'] = exercise_type.replace('_', '-')
                                ex_data['id'] = ex_data.get('id', f'question_{question_index}')
                                questions.append(ex_data)
                                question_index += 1

                for i, question in enumerate(questions):
                    if not question.get('id'):
                        question['id'] = f'question_{i + 1}'

            except Exception as e:
                print(f"Error parsing questions: {e}")
                return Response(
                    {'detail': 'Error parsing lesson questions.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        # Find the specific question
        question = None
        for q in questions:
            q_id = str(q.get('id', ''))
            if q_id == str(exercise_id):
                question = q
                break

        if not question:
            return Response(
                {'detail': f'Question with ID {exercise_id} not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check correctness based on question type
        is_correct = False
        correct_answer = None
        question_type = question.get('type', 'multiple-choice')

        print(f"\n=== Processing Question {exercise_id} ===")
        print(f"Type: {question_type}")
        print(f"Submitted answer: '{submitted_answer}'")

        if question_type == 'multiple-choice':
            correct_answer = question.get('correct_answer', question.get('correct', 0))
            is_correct = int(submitted_answer) == int(correct_answer)

        elif question_type in ['fill-blank', 'fill_blank']:
            if 'answers' in question and question['answers']:
                correct_answer = question['answers'][0]
            elif 'answer' in question:
                correct_answer = question['answer']
            elif 'correct_answer' in question:
                correct_answer = question['correct_answer']
            elif 'correct' in question:
                correct_answer = question['correct']
            else:
                return Response(
                    {'detail': 'Question is missing answer configuration.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if correct_answer is not None:
                def normalize_answer(ans):
                    if ans is None:
                        return ""
                    normalized = str(ans).strip().lower()
                    normalized = ' '.join(normalized.split())
                    return normalized

                correct_normalized = normalize_answer(correct_answer)
                submitted_normalized = normalize_answer(submitted_answer)
                is_correct = correct_normalized == submitted_normalized

        elif question_type == 'paragraph':
            is_correct = True
            correct_answer = "Answer saved successfully"

        elif question_type in ['true-false', 'true_false']:
            correct_answer = question.get('correct_answer', question.get('correct', 0))
            is_correct = int(submitted_answer) == int(correct_answer)

        # ✅ CRITICAL FIX: Initialize submission_data if needed
        if not student_exercise.submission_data:
            student_exercise.submission_data = {}

        # Check if this question was already answered correctly
        previous_submission = student_exercise.submission_data.get(str(exercise_id), {})
        was_previously_correct = previous_submission.get('is_correct', False)

        # Store submission
        student_exercise.submission_data[str(exercise_id)] = {
            'answer': submitted_answer,
            'is_correct': is_correct,
            'submitted_at': timezone.now().isoformat(),
            'question_type': question_type
        }

        # ✅ CRITICAL FIX: Update score properly
        # If this answer is correct and wasn't correct before, add 1 to score
        if is_correct and not was_previously_correct:
            student_exercise.score = float(student_exercise.score or 0) + 1.0
            print(f"✅ Correct answer! New score: {student_exercise.score}")
        elif not is_correct and was_previously_correct:
            # If changing from correct to incorrect (rare case)
            student_exercise.score = max(0, float(student_exercise.score or 0) - 1.0)
            print(f"⚠️ Answer changed to incorrect. New score: {student_exercise.score}")
        else:
            print(f"ℹ️ Score unchanged: {student_exercise.score}")

        # Check completion
        total_questions = len(questions)
        completed_questions = sum(
            1 for q in questions
            if student_exercise.submission_data.get(str(q.get('id', '')), {}).get('is_correct')
        )

        print(f"📊 Progress: {completed_questions}/{total_questions} questions answered correctly")

        # Mark as completed if all questions answered correctly
        if total_questions > 0 and completed_questions >= total_questions:
            student_exercise.completed = True
            if not student_exercise.completed_at:
                student_exercise.completed_at = timezone.now()
            print(f"🎉 Lesson completed! Final score: {student_exercise.score}/{total_questions}")

        # ✅ SAVE TO DATABASE
        student_exercise.save()

        # ✅ VERIFY SAVE
        student_exercise.refresh_from_db()
        print(f"✅ Saved to DB - Score: {student_exercise.score}, Completed: {student_exercise.completed}")

        response_data = {
            'detail': 'Answer submitted successfully.',
            'question_id': exercise_id,
            'submitted_answer': submitted_answer,
            'is_correct': is_correct,
            'score': float(student_exercise.score),
            'total_questions': total_questions,
            'completed_questions': completed_questions,
            'lesson_completed': student_exercise.completed,
            'completed_at': student_exercise.completed_at.isoformat() if student_exercise.completed_at else None
        }

        if not is_correct and question_type != 'paragraph':
            response_data['correct_answer'] = correct_answer

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"❌ ERROR in submit_exercise_answer: {e}")
        import traceback
        traceback.print_exc()
        return Response(
            {'detail': f'Server error: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def submit_followup_answer(request, lesson_id, exercise_id):
    """
    API endpoint for students to submit follow-up exercise answers
    """
    user = request.user

    # Get the lesson and validate enrollment
    lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)

    enrollment = Enrollment.objects.filter(
        student=user,
        course=lesson.course,
        status__in=['approved', 'completed']
    ).first()

    if not enrollment:
        return Response(
            {'detail': 'You are not enrolled in this course.'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Get or create student exercise record
    student_exercise, created = StudentExercise.objects.get_or_create(
        student=user,
        lesson=lesson,
        defaults={'completed': False, 'score': 0.0}
    )

    # Get submitted answer
    submitted_answer = request.data.get('answer')
    if submitted_answer is None:
        return Response(
            {'detail': 'Answer is required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Locate the exercise and its follow-up
    exercise = None
    follow_up_data = None

    if lesson.exercise:
        try:
            if isinstance(lesson.exercise, list):
                exercise = next((ex for ex in lesson.exercise if str(ex.get('id')) == str(exercise_id)), None)
            elif isinstance(lesson.exercise, dict):
                if 'questions' in lesson.exercise:
                    exercise = next((ex for ex in lesson.exercise['questions'] if str(ex.get('id')) == str(exercise_id)), None)
                elif str(lesson.exercise.get('id')) == str(exercise_id):
                    exercise = lesson.exercise

            if exercise:
                # Get follow-up data
                if 'follow_up' in exercise:
                    follow_up_data = exercise['follow_up']
                elif exercise.get('type') == 'multiple-choice' and exercise.get('options'):
                    # Generate auto follow-up
                    correct_option = exercise.get('options', [])[exercise.get('correct', 0)]
                    question_snippet = exercise.get('question', '')[:50]
                    follow_up_data = {
                        'question': f'Complete this sentence: The correct answer to "{question_snippet}..." is _______.',
                        'correct_answer': correct_option,
                        'explanation': f'The correct answer is "{correct_option}". This reinforces your understanding of the concept.'
                    }

        except Exception as e:
            print(f"Error finding exercise: {e}")

    if not exercise or not follow_up_data:
        return Response(
            {'detail': 'Exercise or follow-up question not found.'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Check correctness of follow-up answer
    correct_answer = follow_up_data.get('correct_answer', '')
    is_correct = str(submitted_answer).strip().lower() == str(correct_answer).strip().lower()

    # Update score for follow-up (bonus points)
    if is_correct:
        student_exercise.score += 0.5  # Half point for follow-up

    # Store follow-up answer in additional data
    if not student_exercise.additional_data:
        student_exercise.additional_data = {}

    student_exercise.additional_data[f'followup_{exercise_id}'] = {
        'answer': submitted_answer,
        'correct': is_correct,
        'timestamp': timezone.now().isoformat()
    }

    student_exercise.save()

    return Response({
        'detail': 'Follow-up answer submitted successfully.',
        'exercise_id': exercise_id,
        'submitted_answer': submitted_answer,
        'correct_answer': correct_answer,
        'is_correct': is_correct,
        'explanation': follow_up_data.get('explanation', ''),
        'score': student_exercise.score,
        'completed': student_exercise.completed
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_exercise_progress(request, lesson_id):
    """
    Get detailed progress for all exercises in a lesson including follow-ups
    """
    user = request.user
    lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)

    # Check enrollment
    enrollment = Enrollment.objects.filter(
        student=user,
        course=lesson.course,
        status__in=['approved', 'completed']
    ).first()

    if not enrollment:
        return Response(
            {'detail': 'You are not enrolled in this course.'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Get student exercise record
    student_exercise = StudentExercise.objects.filter(
        student=user,
        lesson=lesson
    ).first()

    progress_data = {
        'lesson_id': lesson_id,
        'completed': student_exercise.completed if student_exercise else False,
        'score': student_exercise.score if student_exercise else 0,
        'exercises': [],
        'follow_up_progress': {}
    }

    if student_exercise and student_exercise.additional_data:
        for key, value in student_exercise.additional_data.items():
            if key.startswith('followup_'):
                exercise_id = key.replace('followup_', '')
                progress_data['follow_up_progress'][exercise_id] = value

    return Response(progress_data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_video_progress(request, lesson_id):
    """
    ✅ FIXED: Properly marks video as completed
    """
    user = request.user

    try:
        lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)

        # Check enrollment
        enrollment = Enrollment.objects.filter(
            student=user,
            course=lesson.course,
            status__in=['approved', 'completed']
        ).first()

        if not enrollment:
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Extract progress data
        video_progress = float(request.data.get('video_progress', 0))
        video_duration = float(request.data.get('video_duration', 0))
        watched_percentage = float(request.data.get('watched_percentage', 0))
        engagement_score = int(request.data.get('engagement_score', 0))
        is_final = request.data.get('is_final', False)

        # ✅ CRITICAL: Determine if video is completed
        video_finished = video_progress >= video_duration * 0.98 if video_duration > 0 else False
        watch_requirement_met = watched_percentage >= 85
        engagement_met = engagement_score >= 7

        # Auto-complete if ALL criteria are met
        should_complete = video_finished and watch_requirement_met and engagement_met

        print(f"\n🎥 VIDEO PROGRESS UPDATE:")
        print(f"   Progress: {video_progress}/{video_duration}")
        print(f"   Watched: {watched_percentage}%")
        print(f"   Engagement: {engagement_score}/10")
        print(f"   Should Complete: {should_complete}")

        # Get or create progress record
        progress, created = LessonProgress.objects.get_or_create(
            student=user,
            lesson=lesson,
            defaults={
                'video_progress': video_progress,
                'video_duration': video_duration,
                'video_completed': should_complete,
                'engagement_data': {
                    'engagement_score': engagement_score,
                    'watched_percentage': watched_percentage,
                }
            }
        )

        if not created:
            # Update existing progress
            progress.video_progress = max(progress.video_progress, video_progress)
            progress.video_duration = video_duration if video_duration > 0 else progress.video_duration

            if not progress.engagement_data:
                progress.engagement_data = {}

            progress.engagement_data.update({
                'engagement_score': max(progress.engagement_data.get('engagement_score', 0), engagement_score),
                'watched_percentage': max(progress.engagement_data.get('watched_percentage', 0), watched_percentage),
            })

            # ✅ CRITICAL: Mark as completed when criteria are met
            if should_complete and not progress.video_completed:
                progress.video_completed = True
                progress.completed_at = timezone.now()
                print(f"   ✅ Video marked as COMPLETED")

        progress.save()

        response_data = {
            'detail': 'Progress updated successfully.',
            'video_progress': progress.video_progress,
            'video_completed': progress.video_completed,
            'watched_percentage': progress.engagement_data.get('watched_percentage', 0),
            'engagement_score': progress.engagement_data.get('engagement_score', 0),
        }

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response(
            {'detail': f'Error updating progress: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_video_progress(request, lesson_id):
    """
    ENHANCED: Retrieve comprehensive video progress with analytics
    """
    user = request.user

    try:
        lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)

        # Check enrollment
        enrollment = Enrollment.objects.filter(
            student=user,
            course=lesson.course,
            status__in=['approved', 'completed']
        ).first()

        if not enrollment:
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get progress record
        progress = LessonProgress.objects.filter(
            student=user,
            lesson=lesson
        ).first()

        # Get student exercise record
        student_exercise = StudentExercise.objects.filter(
            student=user,
            lesson=lesson
        ).first()

        # Calculate lesson progress
        lesson_progress = calculate_lesson_progress(lesson, user)

        # Prepare comprehensive response
        response_data = {
            'video_progress': progress.video_progress if progress else 0,
            'video_duration': progress.video_duration if progress else 0,
            'video_completed': progress.video_completed if progress else False,
            'time_spent': progress.time_spent if progress else 0,
            'last_accessed': progress.last_accessed if progress else None,
            'completed_at': getattr(progress, 'completed_at', None) if progress else None,

            # Enhanced analytics
            'engagement_data': progress.engagement_data if progress and progress.engagement_data else {
                'engagement_score': 0,
                'watched_segments': [],
                'watched_percentage': 0,
                'requirements_met': {},
                'tracking_sessions': []
            },

            # Lesson information
            'lesson_completed': student_exercise.completed if student_exercise else False,
            'lesson_progress': lesson_progress,
            'completion_date': student_exercise.completed_at if student_exercise else None,
            'score': student_exercise.score if student_exercise else 0,

            # Content flags
            'has_video': bool(lesson.video_url),
            'has_exercises': bool(lesson.exercise),
            'video_url': lesson.video_url,

            # Completion requirements
            'completion_requirements': lesson.get_video_requirements()
        }

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error retrieving video progress for lesson {lesson_id}: {str(e)}")
        return Response(
            {'detail': 'Error retrieving progress.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_lesson_completed(request, lesson_id):
    """
    ✅ FIXED: Returns fresh lesson data for real-time sidebar updates
    Prevents infinite loops and ensures proper completion tracking
    """
    user = request.user

    print("\n" + "="*80)
    print("🔵 COMPLETION REQUEST RECEIVED")
    print("="*80)
    print(f"Lesson ID: {lesson_id}")
    print(f"User: {user.email}")

    try:
        lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)

        # Check enrollment
        enrollment = Enrollment.objects.filter(
            student=user,
            course=lesson.course,
            status__in=['approved', 'completed']
        ).first()

        if not enrollment:
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # ✅ CRITICAL: Use transaction to ensure atomic updates
        with transaction.atomic():
            # Get or create student exercise
            student_exercise, created = StudentExercise.objects.select_for_update().get_or_create(
                student=user,
                lesson=lesson,
                defaults={
                    'completed': False,
                    'score': 0.0,
                    'submission_data': {}
                }
            )

            # ✅ PREVENT DUPLICATE COMPLETIONS
            if student_exercise.completed:
                print("⚠️ Lesson already completed, returning cached data")

                # Return fresh lessons for sidebar
                all_lessons = Lesson.objects.filter(
                    course=lesson.course,
                    is_active=True
                ).order_by('order')

                completed_ids = set(
                    StudentExercise.objects.filter(
                        student=user,
                        lesson__course=lesson.course,
                        completed=True
                    ).values_list('lesson_id', flat=True)
                )

                lessons_data = [
                    {
                        'id': l.id,
                        'title': l.title,
                        'description': l.description,
                        'duration': l.duration,
                        'order': l.order,
                        'completed': l.id in completed_ids,
                        'created_at': l.created_at.isoformat() if l.created_at else None
                    }
                    for l in all_lessons
                ]

                return Response({
                    'detail': 'Lesson already completed.',
                    'completed': True,
                    'completed_at': student_exercise.completed_at.isoformat(),
                    'score': student_exercise.score,
                    'updated_lessons': lessons_data,
                    'already_completed': True
                }, status=status.HTTP_200_OK)

            # Check requirements
            completion_check = check_lesson_requirements(lesson, user)

            if not completion_check['can_complete']:
                print("❌ Requirements not met:", completion_check['missing'])
                return Response(
                    {
                        'detail': 'Cannot complete lesson. Requirements not met.',
                        'missing_requirements': completion_check['missing'],
                        'completion_status': completion_check
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get completion data
            reflection = request.data.get('reflection', '').strip()
            score = float(request.data.get('score', 0))
            total_questions = int(request.data.get('total_questions', 0))

            # ✅ MARK AS COMPLETED
            student_exercise.completed = True
            student_exercise.completed_at = timezone.now()
            student_exercise.score = score if score > 0 else 1.0

            if not student_exercise.submission_data:
                student_exercise.submission_data = {}

            student_exercise.submission_data.update({
                'reflection': reflection,
                'completion_timestamp': timezone.now().isoformat(),
                'total_questions': total_questions,
                'completion_method': 'system_tracked',
                'requirements_met': completion_check['requirements_met']
            })

            student_exercise.save()

        # ✅ REFRESH FROM DATABASE (outside transaction)
        student_exercise.refresh_from_db()
        print(f"✅ Saved - Completed: {student_exercise.completed}")

        # ✅ FETCH FRESH LESSONS FOR SIDEBAR
        print("\n🔍 Fetching fresh lesson data...")

        all_lessons = Lesson.objects.filter(
            course=lesson.course,
            is_active=True
        ).select_related('course').order_by('order')

        # Query completed lesson IDs AFTER completion
        completed_ids = set(
            StudentExercise.objects.filter(
                student=user,
                lesson__course=lesson.course,
                completed=True
            ).values_list('lesson_id', flat=True)
        )

        print(f"✅ Found {len(completed_ids)} completed lessons")
        print(f"Completed IDs: {sorted(completed_ids)}")

        # Build fresh lessons array
        lessons_data = []
        for lesson_item in all_lessons:
            is_completed = lesson_item.id in completed_ids

            lesson_data = {
                'id': lesson_item.id,
                'title': lesson_item.title,
                'description': lesson_item.description,
                'duration': lesson_item.duration,
                'order': lesson_item.order,
                'completed': is_completed,
                'created_at': lesson_item.created_at.isoformat() if lesson_item.created_at else None
            }

            lessons_data.append(lesson_data)

        # Calculate progress
        total_lessons = len(lessons_data)
        completed_lessons = len(completed_ids)
        progress_percentage = round((completed_lessons / total_lessons) * 100, 1) if total_lessons > 0 else 0

        print(f"\n📊 Progress: {completed_lessons}/{total_lessons} ({progress_percentage}%)")

        # ✅ BUILD RESPONSE WITH FRESH DATA
        response_data = {
            'detail': 'Lesson completed successfully!',
            'completed': True,
            'completed_at': student_exercise.completed_at.isoformat(),
            'score': student_exercise.score,
            'total_questions': total_questions,

            # ✅ CRITICAL: Fresh lessons for sidebar
            'updated_lessons': lessons_data,

            'course_progress': progress_percentage,
            'total_lessons': total_lessons,
            'completed_lessons': completed_lessons,
            'sidebar_update': True,
            'timestamp': timezone.now().isoformat()
        }

        print("✅ COMPLETION SUCCESSFUL")
        print("="*80 + "\n")

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

        return Response(
            {'detail': f'Error completing lesson: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def check_lesson_requirements(lesson, user):
    """
    ✅ FIXED: Properly validates ALL requirements before allowing completion
    """
    missing_requirements = []
    requirements_met = {}

    try:
        # ✅ CRITICAL: Check video completion (if exists)
        if lesson.video_url:
            from admin_dashboard.models import LessonProgress

            video_progress = LessonProgress.objects.filter(
                student=user,
                lesson=lesson
            ).first()

            # ✅ FIXED: Must have video_progress AND it must be marked completed
            video_completed = (
                video_progress is not None and
                video_progress.video_completed == True
            )

            requirements_met['video_completed'] = video_completed

            if not video_completed:
                missing_requirements.append('video_completion')
                print(f"❌ Video requirement NOT met for lesson {lesson.id}")
                print(f"   - video_progress exists: {video_progress is not None}")
                if video_progress:
                    print(f"   - video_completed: {video_progress.video_completed}")
        else:
            # No video = requirement automatically met
            requirements_met['video_completed'] = True

        # ✅ Check exercise completion (if exists)
        if lesson.exercise:
            exercise_score = calculate_exercise_completion_score(lesson, user)
            requirements_met['exercises_completed'] = exercise_score >= 1.0

            if exercise_score < 1.0:
                missing_requirements.append('exercises_incomplete')
                print(f"❌ Exercise requirement NOT met for lesson {lesson.id}")
                print(f"   - completion score: {exercise_score}")
        else:
            # No exercises = requirement automatically met
            requirements_met['exercises_completed'] = True

        can_complete = len(missing_requirements) == 0

        print(f"\n✅ Lesson {lesson.id} completion check:")
        print(f"   - Can complete: {can_complete}")
        print(f"   - Missing: {missing_requirements}")
        print(f"   - Requirements met: {requirements_met}")

        return {
            'can_complete': can_complete,
            'missing': missing_requirements,
            'requirements_met': requirements_met
        }

    except Exception as e:
        logger.warning(f"Error checking requirements: {e}")
        print(f"❌ Error in requirement check: {e}")
        import traceback
        traceback.print_exc()
        return {
            'can_complete': False,
            'missing': ['validation_error'],
            'requirements_met': {}
        }


def check_lesson_requirements(lesson, user):
    """
    Check if all lesson requirements are met
    """
    missing_requirements = []
    requirements_met = {}

    try:
        # Check video completion (if exists)
        if lesson.video_url:
            from admin_dashboard.models import LessonProgress

            video_progress = LessonProgress.objects.filter(
                student=user,
                lesson=lesson
            ).first()

            video_completed = video_progress and video_progress.video_completed
            requirements_met['video_completed'] = video_completed

            if not video_completed:
                missing_requirements.append('video_completion')

        # Check exercise completion (if exists)
        if lesson.exercise:
            exercise_score = calculate_exercise_completion_score(lesson, user)
            requirements_met['exercises_completed'] = exercise_score >= 1.0

            if exercise_score < 1.0:
                missing_requirements.append('exercises_incomplete')
        else:
            requirements_met['exercises_completed'] = True

        can_complete = len(missing_requirements) == 0

        return {
            'can_complete': can_complete,
            'missing': missing_requirements,
            'requirements_met': requirements_met
        }

    except Exception as e:
        logger.warning(f"Error checking requirements: {e}")
        return {
            'can_complete': False,
            'missing': ['validation_error'],
            'requirements_met': {}
        }

def calculate_exercise_completion_score(lesson, user):
    """Calculate completion score for exercises (0.0 to 1.0)"""
    try:
        student_exercise = StudentExercise.objects.filter(
            student=user,
            lesson=lesson
        ).first()

        if not student_exercise or not student_exercise.submission_data:
            return 0.0

        # Count total exercises
        total_exercises = 0
        if isinstance(lesson.exercise, list):
            total_exercises = len(lesson.exercise)
        elif isinstance(lesson.exercise, dict):
            if 'questions' in lesson.exercise:
                total_exercises = len(lesson.exercise.get('questions', []))
            else:
                exercise_types = ['multiple_choice', 'fill_blank', 'paragraph', 'true_false']
                total_exercises = sum(1 for ex_type in exercise_types if ex_type in lesson.exercise)

        if total_exercises == 0:
            return 1.0

        # Count completed questions
        completed_exercises = 0
        for i in range(1, total_exercises + 1):
            question_key = f'question_{i}'
            if question_key in student_exercise.submission_data:
                submission = student_exercise.submission_data[question_key]
                if submission.get('is_correct') or submission.get('question_type') == 'paragraph':
                    completed_exercises += 1

        return completed_exercises / total_exercises

    except Exception as e:
        logger.warning(f"Error calculating exercise score: {e}")
        return 0.0

def calculate_lesson_progress(lesson, user):
    """
    ENHANCED: Calculate comprehensive lesson progress based on all components
    Returns detailed progress information for real-time tracking
    """
    progress_components = []
    component_details = {}

    try:
        # Video component (if exists)
        if lesson.video_url:
            video_progress = LessonProgress.objects.filter(
                student=user,
                lesson=lesson
            ).first()

            video_completed = video_progress.video_completed if video_progress else False
            video_score = 1.0 if video_completed else 0.0

            if video_progress and video_progress.engagement_data:
                # Enhanced video scoring based on engagement
                engagement_score = video_progress.engagement_data.get('engagement_score', 0)
                watched_percentage = video_progress.engagement_data.get('watched_percentage', 0)

                # Weighted score: 70% completion, 20% engagement, 10% watch coverage
                if video_completed:
                    video_score = (0.7 * 1.0 +
                                 0.2 * (engagement_score / 10) +
                                 0.1 * (watched_percentage / 100))
                else:
                    video_score = min(0.5, watched_percentage / 100)  # Partial credit for watching

            progress_components.append(video_score)
            component_details['video'] = {
                'completed': video_completed,
                'score': video_score,
                'engagement_score': video_progress.engagement_data.get('engagement_score', 0) if video_progress and video_progress.engagement_data else 0,
                'watched_percentage': video_progress.engagement_data.get('watched_percentage', 0) if video_progress and video_progress.engagement_data else 0
            }

        # Exercise component (if exists)
        if lesson.exercise:
            exercise_score = calculate_exercise_completion_score(lesson, user)
            progress_components.append(exercise_score)
            component_details['exercises'] = {
                'completed': exercise_score >= 1.0,
                'score': exercise_score
            }

        # Calculate overall progress
        if not progress_components:
            overall_progress = 100.0  # No components means lesson is essentially complete
            can_complete = True
        else:
            overall_progress = sum(progress_components) / len(progress_components) * 100
            can_complete = all(score >= 1.0 for score in progress_components)

        return {
            'progress_percentage': round(overall_progress, 1),
            'can_complete': can_complete,
            'component_details': component_details,
            'total_components': len(progress_components),
            'completed_components': sum(1 for score in progress_components if score >= 1.0)
        }

    except Exception as e:
        logger.warning(f"Error calculating lesson progress for lesson {lesson.id}: {e}")
        return {
            'progress_percentage': 0.0,
            'can_complete': False,
            'component_details': {},
            'total_components': 0,
            'completed_components': 0
        }
def check_lesson_requirements(lesson, user):
    """
    ENHANCED: Check if all lesson requirements are met with detailed feedback
    """
    missing_requirements = []
    requirements_met = {}

    try:
        # Check video completion (if video exists)
        if lesson.video_url:
            video_progress = LessonProgress.objects.filter(
                student=user,
                lesson=lesson
            ).first()

            video_completed = video_progress and video_progress.video_completed
            requirements_met['video_completed'] = video_completed

            if video_completed:
                # Check engagement requirements
                if video_progress.engagement_data:
                    engagement_score = video_progress.engagement_data.get('engagement_score', 0)
                    watched_percentage = video_progress.engagement_data.get('watched_percentage', 0)

                    video_requirements = lesson.get_video_requirements()
                    min_engagement = video_requirements.get('min_engagement_score', 7)
                    min_watch = video_requirements.get('min_watch_percentage', 90)

                    requirements_met['video_engagement'] = engagement_score >= min_engagement
                    requirements_met['video_watched'] = watched_percentage >= min_watch

                    if engagement_score < min_engagement:
                        missing_requirements.append(f'video_engagement (score: {engagement_score}/{min_engagement})')
                    if watched_percentage < min_watch:
                        missing_requirements.append(f'video_coverage ({watched_percentage:.1f}% watched, need {min_watch}%)')
                else:
                    requirements_met['video_engagement'] = False
                    requirements_met['video_watched'] = False
                    missing_requirements.extend(['video_engagement', 'video_coverage'])
            else:
                missing_requirements.append('video_completion')
                requirements_met['video_engagement'] = False
                requirements_met['video_watched'] = False

        # Check exercise completion (if exercises exist)
        if lesson.exercise:
            exercise_score = calculate_exercise_completion_score(lesson, user)
            requirements_met['exercises_completed'] = exercise_score >= 1.0

            if exercise_score < 1.0:
                try:
                    total_exercises = 0

                    if isinstance(lesson.exercise, list):
                        total_exercises = len(lesson.exercise)
                    elif isinstance(lesson.exercise, dict):
                        if 'questions' in lesson.exercise:
                            total_exercises = len(lesson.exercise.get('questions', []))
                        else:
                            exercise_types = ['multiple_choice', 'fill_blank', 'paragraph', 'true_false']
                            total_exercises = sum(1 for ex_type in exercise_types if ex_type in lesson.exercise)

                    actual_completed = int(exercise_score * total_exercises)
                    missing_requirements.append(f'exercises ({actual_completed}/{total_exercises} completed)')

                except Exception:
                    missing_requirements.append('exercises (incomplete)')
        else:
            requirements_met['exercises_completed'] = True

        can_complete = len(missing_requirements) == 0

        return {
            'can_complete': can_complete,
            'missing': missing_requirements,
            'requirements_met': requirements_met,
            'total_requirements': len([k for k in requirements_met.keys()]),
            'met_requirements': len([k for k, v in requirements_met.items() if v])
        }

    except Exception as e:
        logger.warning(f"Error checking lesson requirements for lesson {lesson.id}: {e}")
        return {
            'can_complete': False,
            'missing': ['validation_error'],
            'requirements_met': {},
            'total_requirements': 0,
            'met_requirements': 0
        }
def calculate_exercise_completion_score(lesson, user):
    """Calculate completion score for exercises (0.0 to 1.0)"""
    try:
        student_exercise = StudentExercise.objects.filter(
            student=user,
            lesson=lesson
        ).first()

        if not student_exercise or not student_exercise.submission_data:
            return 0.0

        # Count total exercises
        total_exercises = 0
        if isinstance(lesson.exercise, list):
            total_exercises = len(lesson.exercise)
        elif isinstance(lesson.exercise, dict):
            if 'questions' in lesson.exercise:
                total_exercises = len(lesson.exercise.get('questions', []))
            else:
                exercise_types = ['multiple_choice', 'fill_blank', 'paragraph', 'true_false']
                total_exercises = sum(1 for ex_type in exercise_types if ex_type in lesson.exercise)

        if total_exercises == 0:
            return 1.0

        # Count completed questions
        completed_exercises = 0
        for i in range(1, total_exercises + 1):
            question_key = f'question_{i}'
            if question_key in student_exercise.submission_data:
                submission = student_exercise.submission_data[question_key]
                if submission.get('is_correct') or submission.get('question_type') == 'paragraph':
                    completed_exercises += 1

        return completed_exercises / total_exercises

    except Exception as e:
        logger.warning(f"Error calculating exercise score: {e}")
        return 0.0
def calculate_course_progress(course, user):
    """Calculate overall course progress for sidebar updates"""
    try:
        total_lessons = Lesson.objects.filter(course=course, is_active=True).count()

        if total_lessons == 0:
            return {
                'total_lessons': 0,
                'completed_lessons': 0,
                'progress_percentage': 100.0
            }

        # Assuming StudentExercise tracks completed lessons
        completed_lessons = StudentExercise.objects.filter(
            lesson__course=course,
            lesson__is_active=True,
            user=user,
            is_completed=True  # Assumes there's a boolean field to indicate completion
        ).values('lesson').distinct().count()

        progress_percentage = (completed_lessons / total_lessons) * 100

        return {
            'total_lessons': total_lessons,
            'completed_lessons': completed_lessons,
            'progress_percentage': round(progress_percentage, 2)
        }

    except Exception as e:
        # You might want to log this exception in production
        return {
            'total_lessons': 0,
            'completed_lessons': 0,
            'progress_percentage': 0.0,
            'error': str(e)
        }
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_lesson_with_video(request, lesson_id):
    """
    Enhanced endpoint to retrieve lesson with properly configured video metadata
    """
    user = request.user

    try:
        lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)

        # Check enrollment
        enrollment = Enrollment.objects.filter(
            student=user,
            course=lesson.course,
            status__in=['approved', 'completed']
        ).first()

        if not enrollment:
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Build video configuration
        video_config = None
        if lesson.video_url:
            video_config = build_video_config(lesson)

        # Serialize lesson data
        lesson_data = {
            'id': lesson.id,
            'title': lesson.title,
            'description': lesson.description,
            'content': lesson.content,
            'video_url': lesson.video_url,
            'video_config': video_config,
            'duration': lesson.duration,
            'order': lesson.order,
            'course_title': lesson.course.title,
            'course_code': lesson.course.code,
        }

        return Response(lesson_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {'detail': f'Error retrieving lesson: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
def build_video_config(lesson):
    """
    Build comprehensive video configuration for frontend
    """
    if not lesson.video_url:
        return None

    url = lesson.video_url.lower()

    # Detect source and format
    if 'youtube.com' in url or 'youtu.be' in url:
        source = 'youtube'
        format_type = 'youtube'
        embed_url = lesson.get_youtube_embed_url()
        mime_type = None
        supports_streaming = True
        requires_proxy = False

    elif 'vimeo.com' in url:
        source = 'vimeo'
        format_type = 'vimeo'
        embed_url = lesson.get_vimeo_embed_url()
        mime_type = None
        supports_streaming = True
        requires_proxy = False

    elif '/media/' in url or 'localhost' in url:
        source = 'local'
        format_type = lesson.video_format or 'mp4'
        embed_url = None
        mime_type = f'video/{format_type}'
        supports_streaming = True
        requires_proxy = True

    else:
        source = 'external'
        format_type = lesson.video_format or 'mp4'
        embed_url = None
        mime_type = f'video/{format_type}'
        supports_streaming = True
        requires_proxy = False

    # Build final configuration
    config = {
        'url': lesson.video_url,
        'source': source,
        'format': format_type,
        'mime_type': mime_type,
        'duration': lesson.video_duration or 0,
        'file_size': lesson.video_file_size or 0,
        'supports_streaming': supports_streaming,
        'requires_authentication': lesson.requires_authentication,
        'allow_download': lesson.allow_download,
        'requires_proxy': requires_proxy,
    }

    if embed_url:
        config['embed_url'] = embed_url

    if source == 'local':
        # Provide streaming URL for local files
        config['streaming_url'] = f'http://localhost:8000{lesson.video_url}'

    return config

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def debug_enrollments(request):
    """Debug endpoint to check user enrollments"""
    user = request.user
    enrollments = Enrollment.objects.filter(student=user)

    enrollment_data = []
    for enrollment in enrollments:
        enrollment_data.append({
            'course': enrollment.course.title,
            'status': enrollment.status,
            'enrolled_at': enrollment.enrolled_at
        })

    return Response({
        'user_id': user.id,
        'user_email': user.email,
        'enrollments': enrollment_data,
        'total_enrollments': len(enrollment_data)
    })

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_grades_summary(request):
    """Get student's grade summary"""
    user = request.user

    # Get all completed exercises
    completed_exercises = StudentExercise.objects.filter(
        student=user,
        completed=True
    ).select_related('lesson')

    total_score = 0
    count = 0

    for exercise in completed_exercises:
        if exercise.score:
            total_score += exercise.score
            count += 1

    average_grade = round((total_score / count) * 100) if count > 0 else 0

    return Response({
        'average_grade': average_grade,
        'total_completed': count,
        'total_score': total_score
    })

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_exercises_list(request):
    """
    API endpoint to get all student exercises for grade calculation
    """
    user = request.user

    try:
        exercises = StudentExercise.objects.filter(
            student=user
        ).select_related('lesson', 'lesson__course').order_by('-completed_at')

        exercise_data = []
        for exercise in exercises:
            exercise_data.append({
                'id': exercise.id,
                'lesson_title': exercise.lesson.title,
                'course_title': exercise.lesson.course.title,
                'completed': exercise.completed,
                'completed_at': exercise.completed_at,
                'score': exercise.score,
                'max_score': 1.0,  # Assuming exercises are scored out of 1.0
                'percentage': exercise.score * 100 if exercise.score else 0
            })

        return Response(exercise_data)

    except Exception as e:
        print(f"Error fetching student exercises: {e}")
        return Response([], status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_completed_exercises(request):
    """
    ✅ FIXED: Calculates average grade including incomplete exercises as 0%
    Average = (sum of all scores) / (total number of ALL exercises in enrolled courses)
    This gives a true overall grade across all courses
    """
    user = request.user

    try:
        # Get all enrolled courses
        enrolled_courses = Course.objects.filter(
            admin_enrollments__student=user,
            admin_enrollments__status__in=['approved', 'completed'],
            is_active=True
        ).distinct()

        if not enrolled_courses.exists():
            return Response({
                'completed_exercises': [],
                'total_completed': 0,
                'average_grade': 0,
                'statistics': {
                    'total_score': 0,
                    'total_possible': 0,
                    'total_exercises': 0
                }
            })

        # Get ALL lessons with exercises (completed AND incomplete)
        all_lessons_with_exercises = Lesson.objects.filter(
            course__in=enrolled_courses,
            is_active=True
        ).exclude(exercise__isnull=True).exclude(exercise={})

        total_lessons_count = all_lessons_with_exercises.count()

        if total_lessons_count == 0:
            return Response({
                'completed_exercises': [],
                'total_completed': 0,
                'average_grade': 0,
                'statistics': {
                    'total_score': 0,
                    'total_possible': 0,
                    'total_exercises': 0
                }
            })

        # Get completed exercises
        completed_exercises = StudentExercise.objects.filter(
            student=user,
            lesson__in=all_lessons_with_exercises,
            completed=True
        ).select_related('lesson', 'lesson__course')

        exercises_data = []
        total_score_sum = 0  # Sum of all scores earned
        total_possible_sum = 0  # Sum of all possible scores (for ALL lessons)
        completed_count = completed_exercises.count()

        # Process ALL lessons (to calculate total possible)
        for lesson in all_lessons_with_exercises:
            # Count questions in this lesson
            question_count = 0

            if lesson.exercise:
                try:
                    if isinstance(lesson.exercise, list):
                        question_count = len(lesson.exercise)
                    elif isinstance(lesson.exercise, dict):
                        if 'questions' in lesson.exercise:
                            question_count = len(lesson.exercise.get('questions', []))
                        else:
                            question_types = ['multiple_choice', 'fill_blank', 'paragraph', 'true_false']
                            question_count = sum(1 for q_type in question_types if q_type in lesson.exercise)

                    if question_count == 0:
                        question_count = 1
                except Exception as e:
                    print(f"Error counting questions for lesson {lesson.id}: {e}")
                    question_count = 1
            else:
                question_count = 1

            # Add to total possible (all lessons)
            total_possible_sum += question_count

            # Check if this lesson is completed
            student_exercise = completed_exercises.filter(lesson=lesson).first()

            if student_exercise:
                # Get actual score
                student_score = float(student_exercise.score) if student_exercise.score is not None else 0.0
                total_score_sum += student_score

                # Add to completed exercises data
                exercise_percentage = (student_score / question_count) * 100 if question_count > 0 else 0

                exercises_data.append({
                    'id': student_exercise.id,
                    'lesson_title': lesson.title,
                    'course_title': lesson.course.title,
                    'score': student_score,
                    'max_score': float(question_count),
                    'score_percentage': round(exercise_percentage, 1),
                    'completed_at': student_exercise.completed_at.isoformat() if student_exercise.completed_at else None
                })
            else:
                # Incomplete lesson - score is 0 (but still counts toward total possible)
                pass

        # ✅ CRITICAL FIX: Calculate average grade across ALL exercises
        # Including incomplete ones (which have 0 score)
        if total_possible_sum > 0:
            average_grade = (total_score_sum / total_possible_sum) * 100
        else:
            average_grade = 0

        print(f"\n📊 Grade Statistics:")
        print(f"   Total Lessons with Exercises: {total_lessons_count}")
        print(f"   Completed Exercises: {completed_count}")
        print(f"   Total Score Earned: {total_score_sum}")
        print(f"   Total Possible Score: {total_possible_sum}")
        print(f"   Average Grade: {average_grade}%")
        print(f"   Completion Rate: {(completed_count / total_lessons_count * 100):.1f}%")

        return Response({
            'completed_exercises': exercises_data,
            'total_completed': completed_count,
            'average_grade': round(average_grade, 1),
            'statistics': {
                'total_score': round(total_score_sum, 1),
                'total_possible': round(total_possible_sum, 1),
                'total_exercises': total_lessons_count,
                'completion_rate': round((completed_count / total_lessons_count * 100), 1) if total_lessons_count > 0 else 0
            }
        })

    except Exception as e:
        print(f"❌ Error fetching completed exercises: {e}")
        import traceback
        traceback.print_exc()

        return Response({
            'completed_exercises': [],
            'total_completed': 0,
            'average_grade': 0,
            'statistics': {
                'total_score': 0,
                'total_possible': 0,
                'total_exercises': 0
            }
        }, status=status.HTTP_200_OK)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_pending_exercises(request):

    """
    API endpoint to get pending (incomplete) exercises count
    """
    user = request.user

    try:
        # Get all enrolled courses with exercises
        enrolled_courses = Course.objects.filter(
            admin_enrollments__student=user,
            admin_enrollments__status__in=['approved', 'completed'],
            is_active=True
        ).distinct()

        total_exercises = 0
        completed_exercises = 0

        for course in enrolled_courses:
            lessons = Lesson.objects.filter(course=course, is_active=True)

            for lesson in lessons:
                if lesson.exercise:
                    try:
                        if isinstance(lesson.exercise, list):
                            total_exercises += len(lesson.exercise)
                        elif isinstance(lesson.exercise, dict):
                            if 'questions' in lesson.exercise:
                                total_exercises += len(lesson.exercise.get('questions', []))
                            else:
                                total_exercises += 1
                        else:
                            total_exercises += 1
                    except Exception:
                        total_exercises += 1

        # Count completed exercises
        completed_exercises = StudentExercise.objects.filter(
            student=user,
            completed=True
        ).count()

        pending_exercises = max(0, total_exercises - completed_exercises)

        return Response({
            'total_exercises': total_exercises,
            'completed_exercises': completed_exercises,
            'pending_exercises': pending_exercises
        })

    except Exception as e:
        print(f"❌ Error calculating pending exercises: {e}")
        return Response({
            'total_exercises': 0,
            'completed_exercises': 0,
            'pending_exercises': 0
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def debug_student_scores(request):
    """
    Debug endpoint to check actual scores in database
    """
    user = request.user

    exercises = StudentExercise.objects.filter(student=user).select_related('lesson')

    debug_data = []
    for ex in exercises:
        debug_data.append({
            'lesson_id': ex.lesson.id,
            'lesson_title': ex.lesson.title,
            'completed': ex.completed,
            'score': ex.score,
            'score_type': type(ex.score).__name__,
            'submission_data': ex.submission_data
        })

    print("\n" + "="*80)
    print("🔍 DATABASE SCORES DEBUG")
    print("="*80)
    for item in debug_data:
        print(f"Lesson: {item['lesson_title']}")
        print(f"  Completed: {item['completed']}")
        print(f"  Score: {item['score']} (type: {item['score_type']})")
        print(f"  Submissions: {len(item['submission_data'])} answers")
        print("-"*80)

    return Response(debug_data)

#guest
class GuestCourseListView(generics.ListAPIView):
    """
    API endpoint for guests to view ALL available courses WITH VIDEO COUNTS
    """
    permission_classes = [AllowAny]

    def get_queryset(self):
        # Return ALL active courses from guest settings
        settings = GuestAccessSettings.objects.first()
        if settings and settings.allowed_courses.exists():
            return settings.allowed_courses.filter(is_active=True).order_by('title')
        else:
            # Fallback to all active courses
            return Course.objects.filter(is_active=True).order_by('title')

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()

            print(f"🔍 Found {queryset.count()} active courses for guest access")

            # ✅ FIXED: Prepare course data WITH VIDEO COUNTS
            course_data = []
            for course in queryset:
                # Get actual lessons count
                lessons_count = course.lessons.filter(is_active=True).count()

                # ✅ CRITICAL FIX: Calculate video count for this course
                video_count = Lesson.objects.filter(
                    course=course,
                    is_active=True
                ).exclude(
                    Q(video_url__isnull=True) |
                    Q(video_url='') |
                    Q(video_url='null')
                ).count()

                # Get teacher name
                teacher_name = course.teacher_name

                # ✅ FIXED: Include video_count in the response
                course_info = {
                    'id': course.id,
                    'title': course.title,
                    'description': course.description,
                    'code': course.code,
                    'duration': course.duration,
                    'price': float(course.price),
                    'lessons_count': lessons_count,
                    'video_count': video_count,
                    'teacher_name': teacher_name,
                    'is_active': course.is_active,
                    'created_at': course.created_at.isoformat() if course.created_at else None,
                    'enrollment_status': 'guest_preview',
                    'category': course.display_category,
                    'is_popular': course.safe_is_popular,
                    'is_new': course.safe_is_new,
                    'is_public': course.is_public,
                }
                course_data.append(course_info)
                print(f"📚 Guest Course: {course.title} - Videos: {video_count}, Lessons: {lessons_count}")

            # Get guest settings
            settings = GuestAccessSettings.objects.first()
            max_lessons = settings.max_lessons_access if settings else 3
            session_duration = settings.max_session_time if settings else 600

            response_data = {
                'courses': course_data,  # ✅ This should now include video_count
                'statistics': {
                    'total_courses': len(course_data),
                    'max_lessons_preview': max_lessons,
                    'session_duration_minutes': session_duration // 60,
                    'guest_mode': True
                },
                'guest_access': {
                    'enabled': settings.enabled if settings else True,
                    'max_lessons': max_lessons,
                    'session_time': session_duration
                }
            }

            print(f"✅ Sending {len(course_data)} courses to frontend WITH VIDEO COUNTS")
            return Response(response_data)

        except Exception as e:
            print(f"❌ Guest courses error: {str(e)}")
            import traceback
            traceback.print_exc()

            # Return proper structure even on error
            return Response({
                'courses': [],
                'statistics': {
                    'total_courses': 0,
                    'max_lessons_preview': 3,
                    'session_duration_minutes': 10,
                    'guest_mode': True
                },
                'guest_access': {
                    'enabled': True,
                    'max_lessons': 3,
                    'session_time': 600
                }
            }, status=status.HTTP_200_OK)
@api_view(['POST'])
@permission_classes([AllowAny])
def start_guest_session(request):
    """Start a new guest session - NO AUTH REQUIRED"""
    try:
        print("🔐 Starting guest session...")

        # Get or create guest settings
        settings, created = GuestAccessSettings.objects.get_or_create(
            id=1,
            defaults={
                'enabled': True,
                'max_session_time': 600,
                'max_lessons_access': 3
            }
        )

        if not settings.enabled:
            return Response(
                {'detail': 'Guest access is currently disabled.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # Create guest session
        session = GuestSession.objects.create(
            session_id=uuid.uuid4(),
            expires_at=timezone.now() + timedelta(minutes=10),
            max_session_time=settings.max_session_time,
        )

        # Manually serialize since we're not using a ModelSerializer
        session_data = {
            'session_id': session.session_id,
            'created_at': session.created_at,
            'expires_at': session.expires_at,
            'is_active': session.is_active,
            'time_used': session.time_used,
            'max_session_time': session.max_session_time,
            'remaining_time': session.get_remaining_time(),
            'is_expired': session.is_expired()
        }

        return Response({
            'session': session_data,
            'settings': {
                'max_session_time': settings.max_session_time,
                'max_lessons_access': settings.max_lessons_access
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        print(f"❌ Guest session error: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response(
            {'detail': 'Failed to start guest session.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([AllowAny])
def validate_guest_session(request, session_id):
    """Validate guest session - check if user is authenticated"""
    # If user is authenticated, don't allow guest session validation
    if request.user.is_authenticated:
        return Response(
            {
                'detail': 'User is authenticated. Guest session not needed.',
                'user_authenticated': True,
                'user_type': request.user.profile.user_type if hasattr(request.user, 'profile') else None
            },
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        session = GuestSession.objects.get(session_id=session_id, is_active=True)
    except GuestSession.DoesNotExist:
        return Response(
            {'detail': 'Invalid or expired session.'},
            status=status.HTTP_404_NOT_FOUND
        )

    if session.is_expired():
        session.is_active = False
        session.save()
        return Response(
            {'detail': 'Session has expired.'},
            status=status.HTTP_410_GONE
        )

    # Update time used
    session.time_used += 5
    session.save()

    # Manually serialize
    session_data = {
        'session_id': session.session_id,
        'created_at': session.created_at,
        'expires_at': session.expires_at,
        'is_active': session.is_active,
        'time_used': session.time_used,
        'max_session_time': session.max_session_time,
        'remaining_time': session.get_remaining_time(),
        'is_expired': session.is_expired(),
        'user_authenticated': False  # Add this flag
    }

    return Response(session_data)

@api_view(['GET'])
@permission_classes([AllowAny])
def guest_available_courses(request):
    """
    ✅ FIXED: Get ALL courses available for guest access WITH VIDEO COUNTS
    """
    try:
        settings = GuestAccessSettings.objects.first()

        # ✅ Return ALL active courses (not just allowed ones)
        queryset = Course.objects.filter(is_active=True).order_by('title')

        print(f"🔍 Found {queryset.count()} courses for guest access")

        course_data = []
        for course in queryset:
            total_lessons = course.lessons.filter(is_active=True).count()

            # ✅ Calculate video count
            video_count = Lesson.objects.filter(
                course=course,
                is_active=True
            ).exclude(
                Q(video_url__isnull=True) |
                Q(video_url='') |
                Q(video_url='null')
            ).count()

            teacher_name = None
            if course.teacher and course.teacher.user:
                teacher_name = f"{course.teacher.user.first_name} {course.teacher.user.last_name}".strip()

            course_info = {
                'id': course.id,
                'title': course.title,
                'description': course.description,
                'code': course.code,
                'duration': course.duration,
                'price': float(course.price) if course.price else 0.0,
                'lessons_count': total_lessons,
                'total_lessons': total_lessons,
                'video_count': video_count,  # ✅ CRITICAL
                'teacher_name': teacher_name,
                'is_active': course.is_active,
                'created_at': course.created_at.isoformat() if course.created_at else None,
                'enrollment_status': 'guest_preview',
                'category': course.get_category_display() if hasattr(course, 'get_category_display') else 'General',
                'is_popular': getattr(course, 'is_popular', False),
                'is_new': getattr(course, 'is_new', False),
                'is_public': getattr(course, 'is_public', True),
            }

            course_data.append(course_info)

            print(f"📚 Guest Course: {course.title}")
            print(f"   - Lessons: {total_lessons}")
            print(f"   - Videos: {video_count}")

        max_lessons = settings.max_lessons_access if settings else 3
        session_duration = settings.max_session_time if settings else 600

        response_data = {
            'courses': course_data,
            'statistics': {
                'total_courses': len(course_data),
                'max_lessons_preview': max_lessons,
                'session_duration_minutes': session_duration // 60,
                'guest_mode': True
            },
            'guest_access': {
                'enabled': settings.enabled if settings else True,
                'max_lessons': max_lessons,
                'session_time': session_duration
            }
        }

        print(f"✅ Sending {len(course_data)} courses to frontend WITH VIDEO COUNTS")
        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        print(f"❌ Guest courses error: {str(e)}")
        import traceback
        traceback.print_exc()

        return Response({
            'courses': [],
            'statistics': {
                'total_courses': 0,
                'max_lessons_preview': 3,
                'session_duration_minutes': 10,
                'guest_mode': True
            },
            'guest_access': {
                'enabled': True,
                'max_lessons': 3,
                'session_time': 600
            }
        }, status=status.HTTP_200_OK)


def generate_slug(text):
    """Generate slug matching frontend's generateSlug function"""
    if not text:
        return ''

    # Convert to lowercase
    slug = text.lower()

    # Remove special characters (keep letters, numbers, spaces, hyphens)
    slug = re.sub(r'[^\w\s-]', '', slug)

    # Replace spaces with hyphens
    slug = re.sub(r'\s+', '-', slug)

    # Replace multiple hyphens with single hyphen
    slug = re.sub(r'--+', '-', slug)

    # Trim leading/trailing hyphens and spaces
    slug = slug.strip('- ')

    return slug

def get_lesson_by_slug(course, lesson_slug):
    """
    Get lesson by slug (generated from title)
    """
    try:
        # First try exact match with the new slug generation
        lessons = Lesson.objects.filter(
            course=course,
            is_active=True
        )

        for lesson in lessons:
            # Generate slug from title using the same logic as frontend
            lesson_slug_from_title = generate_slug(lesson.title)

            # Debug logging
            print(f"🔍 Comparing slugs: '{lesson_slug_from_title}' vs '{lesson_slug}'")

            if lesson_slug_from_title == lesson_slug:
                print(f"✅ Exact match found: {lesson.title}")
                return lesson

        # If not found, try case-insensitive and with special character variations
        for lesson in lessons:
            lesson_slug_from_title = generate_slug(lesson.title)
            # Remove any remaining special characters and compare
            clean_backend_slug = re.sub(r'[^\w-]', '', lesson_slug_from_title).lower()
            clean_frontend_slug = re.sub(r'[^\w-]', '', lesson_slug).lower()

            if clean_backend_slug == clean_frontend_slug:
                print(f"✅ Clean match found: {lesson.title}")
                return lesson

        # Try to find by ID (for backward compatibility)
        if lesson_slug.isdigit():
            try:
                lesson = Lesson.objects.get(
                    course=course,
                    id=int(lesson_slug),
                    is_active=True
                )
                print(f"✅ Found by ID fallback: {lesson.title}")
                return lesson
            except Lesson.DoesNotExist:
                pass

        # If still not found, return None
        print(f"❌ No lesson found for slug: {lesson_slug}")
        return None

    except Exception as e:
        print(f"❌ Error in get_lesson_by_slug: {e}")
        import traceback
        traceback.print_exc()
        return None

@api_view(['GET'])
@permission_classes([AllowAny])
def test_lesson(request, course_slug, lesson_slug):
    """ULTRA SIMPLE TEST"""
    return Response({
        'status': 'working',
        'course': course_slug,
        'lesson': lesson_slug,
        'session_id': request.GET.get('session_id', 'none'),
        'message': 'Backend is responding'
    })

# Add this utility function
def slugify(text):
    """Generate URL-friendly slug from text"""
    import re
    import unicodedata

    # Convert to ASCII
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')

    # Convert to lowercase
    text = text.lower()

    # Remove special characters
    text = re.sub(r'[^\w\s-]', '', text)

    # Replace spaces with hyphens
    text = re.sub(r'\s+', '-', text)

    # Remove multiple hyphens
    text = re.sub(r'--+', '-', text)

    # Strip leading/trailing hyphens
    text = text.strip('-')

    return text

@api_view(['GET'])
@permission_classes([AllowAny])
def get_guest_lesson_by_slug(request, course_slug, lesson_slug):
    """
    SIMPLIFIED: Get lesson by slug for guest users
    """
    print(f"📖 GET Lesson: {course_slug}/{lesson_slug}")

    try:
        session_id = request.GET.get('session_id')

        # Validate session
        if not session_id:
            return Response({'error': 'Session ID required'}, status=400)

        # Get session
        try:
            session = GuestSession.objects.get(session_id=session_id, is_active=True)
        except GuestSession.DoesNotExist:
            return Response({'error': 'Invalid or expired session'}, status=410)

        # Check if session expired
        if session.is_expired():
            session.is_active = False
            session.save()
            return Response({'error': 'Session expired'}, status=410)

        # Get course
        try:
            course = Course.objects.get(code=course_slug, is_active=True)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=404)

        # ✅ FIXED: Get ALL lessons for the course
        lessons = Lesson.objects.filter(course=course, is_active=True).order_by('order')

        # Find the specific lesson by slug
        target_lesson = None
        for lesson in lessons:
            # Generate slug from title
            lesson_title_slug = slugify(lesson.title)
            print(f"🔍 Comparing: {lesson_title_slug} == {lesson_slug}")

            if lesson_title_slug == lesson_slug:
                target_lesson = lesson
                break

        # If not found by slug, try by ID
        if not target_lesson and lesson_slug.isdigit():
            try:
                target_lesson = Lesson.objects.get(id=int(lesson_slug), course=course, is_active=True)
            except Lesson.DoesNotExist:
                pass

        if not target_lesson:
            return Response({'error': 'Lesson not found'}, status=404)

        # Parse exercises
        exercises = []
        if target_lesson.exercise:
            exercises = parse_exercises_from_lesson(target_lesson.exercise)

        # Build response
        response_data = {
            'id': target_lesson.id,
            'title': target_lesson.title,
            'description': target_lesson.description or '',
            'content': target_lesson.content or '',
            'video_url': target_lesson.video_url or '',
            'duration': target_lesson.duration or 0,
            'order': target_lesson.order or 0,
            'course_title': course.title,
            'course_code': course.code,
            'course_id': course.id,
            'exercises': exercises,
            'completed': False,
            'video_completed': False,
            'is_guest': True
        }

        print(f"✅ Returning lesson: {target_lesson.title}")
        return Response(response_data)

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response({'error': f'Server error: {str(e)}'}, status=500)
class GuestCourseListView(generics.ListAPIView):
    """
    ✅ FIXED: API endpoint for guests to view ALL available courses WITH VIDEO COUNTS
    """
    permission_classes = [AllowAny]

    def get_queryset(self):
        settings = GuestAccessSettings.objects.first()
        if settings and settings.allowed_courses.exists():
            return settings.allowed_courses.filter(is_active=True).order_by('title')
        else:
            return Course.objects.filter(is_active=True).order_by('title')

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()

            print(f"🔍 Found {queryset.count()} active courses for guest access")

            # ✅ FIXED: Prepare course data WITH VIDEO COUNTS
            course_data = []
            for course in queryset:
                # Get actual lessons count
                lessons_count = course.lessons.filter(is_active=True).count()

                # ✅ CRITICAL FIX: Calculate video count for this course
                video_count = Lesson.objects.filter(
                    course=course,
                    is_active=True
                ).exclude(
                    Q(video_url__isnull=True) |
                    Q(video_url='') |
                    Q(video_url='null')
                ).count()

                # Get teacher name
                teacher_name = None
                if course.teacher and course.teacher.user:
                    teacher_name = f"{course.teacher.user.first_name} {course.teacher.user.last_name}".strip()

                # ✅ FIXED: Include video_count in the response
                course_info = {
                    'id': course.id,
                    'title': course.title,
                    'description': course.description,
                    'code': course.code,
                    'duration': course.duration,
                    'price': float(course.price) if course.price else 0.0,
                    'lessons_count': lessons_count,
                    'total_lessons': lessons_count,  # Backend total
                    'video_count': video_count,  # ✅ THIS IS THE FIX
                    'teacher_name': teacher_name,
                    'is_active': course.is_active,
                    'created_at': course.created_at.isoformat() if course.created_at else None,
                    'enrollment_status': 'guest_preview',
                    'category': course.get_category_display() if hasattr(course, 'get_category_display') else 'General',
                    'is_popular': getattr(course, 'is_popular', False),
                    'is_new': getattr(course, 'is_new', False),
                    'is_public': getattr(course, 'is_public', True),
                }
                course_data.append(course_info)
                print(f"📚 Guest Course: {course.title} - Videos: {video_count}, Lessons: {lessons_count}")

            # Get guest settings
            settings = GuestAccessSettings.objects.first()
            max_lessons = settings.max_lessons_access if settings else 3
            session_duration = settings.max_session_time if settings else 600

            response_data = {
                'courses': course_data,  # ✅ Now includes video_count
                'statistics': {
                    'total_courses': len(course_data),
                    'max_lessons_preview': max_lessons,
                    'session_duration_minutes': session_duration // 60,
                    'guest_mode': True
                },
                'guest_access': {
                    'enabled': settings.enabled if settings else True,
                    'max_lessons': max_lessons,
                    'session_time': session_duration
                }
            }

            print(f"✅ Sending {len(course_data)} courses to frontend WITH VIDEO COUNTS")
            return Response(response_data)

        except Exception as e:
            print(f"❌ Guest courses error: {str(e)}")
            import traceback
            traceback.print_exc()

            return Response({
                'courses': [],
                'statistics': {
                    'total_courses': 0,
                    'max_lessons_preview': 3,
                    'session_duration_minutes': 10,
                    'guest_mode': True
                },
                'guest_access': {
                    'enabled': True,
                    'max_lessons': 3,
                    'session_time': 600
                }
            }, status=status.HTTP_200_OK)

# student_dashboard/views.py - ADD THESE NEW VIEWS

class HomeCourseListView(generics.ListAPIView):
    """
    ✅ NEW: Returns ALL courses for Home components (Home, HomeCourses, LessonOverview, HomeExercise)
    """
    permission_classes = [AllowAny]
    serializer_class = CourseListSerializer

    def get_queryset(self):
        return Course.objects.filter(is_active=True).order_by('title')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        user = request.user

        # Serialize all courses for home display
        all_courses_data = []

        for course in queryset:
            # For home views, we don't need enrollment status for unauthenticated users
            enrollment_status = 'not_enrolled'
            is_enrolled = False

            if user.is_authenticated:
                enrollment = Enrollment.objects.filter(student=user, course=course).first()
                enrollment_status = enrollment.status if enrollment else 'not_enrolled'
                is_enrolled = enrollment_status in ['approved', 'completed', 'enrolled']

            # Get lessons count
            lessons_count = Lesson.objects.filter(course=course, is_active=True).count()

            # Count videos
            video_count = Lesson.objects.filter(
                course=course,
                is_active=True
            ).exclude(
                Q(video_url__isnull=True) |
                Q(video_url='') |
                Q(video_url='null')
            ).count()

            # Count exercises (lessons with exercises)
            exercises_count = 0
            lessons = Lesson.objects.filter(course=course, is_active=True)
            for lesson in lessons:
                if lesson.exercise:
                    exercises_count += 1

            # Calculate progress only for enrolled users
            progress = 0
            if is_enrolled and lessons_count > 0:
                completed_lessons = StudentExercise.objects.filter(
                    student=user,
                    lesson__course=course,
                    completed=True
                ).count()
                progress = round((completed_lessons / lessons_count) * 100, 1)

            # Build course data for home
            course_data = {
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'description': course.description,
                'price': float(course.price) if course.price else 0.0,
                'is_active': course.is_active,
                'progress': progress,
                'completed_lessons': StudentExercise.objects.filter(
                    student=user,
                    lesson__course=course,
                    completed=True
                ).count() if is_enrolled else 0,
                'total_lessons': lessons_count,
                'enrollment_status': enrollment_status,
                'is_enrolled': is_enrolled,
                'total_exercises': exercises_count,
                'video_count': video_count,
                'category': course.get_category_display(),
                'is_popular': course.is_popular,
                'is_new': course.is_new,
                'duration': course.duration,
                'teacher_name': course.teacher_name,
                'created_at': course.created_at.isoformat() if course.created_at else None,
            }

            all_courses_data.append(course_data)

        return Response({
            'courses': all_courses_data,
            'for_home': True,  # Flag to indicate this is for home components
            'total_courses': len(all_courses_data)
        })


class HomeCourseLessonsView(generics.ListAPIView):
    """
    ✅ NEW: Returns ALL lessons for a course for Home components
    """
    permission_classes = [AllowAny]
    serializer_class = LessonListSerializer

    def get_queryset(self):
        course_code = self.kwargs.get('course_code')
        return Lesson.objects.filter(
            course__code=course_code,
            course__is_active=True,
            is_active=True
        ).order_by('order')

    def list(self, request, *args, **kwargs):
        course_code = self.kwargs.get('course_code')
        course = get_object_or_404(Course, code=course_code, is_active=True)

        lessons = self.get_queryset()
        serializer = self.get_serializer(lessons, many=True, context={'request': request})

        return Response({
            'course': {
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'description': course.description,
            },
            'lessons': serializer.data,
            'for_home': True,  # Flag for home components
            'total_lessons': lessons.count()
        })


class HomeLessonDetailView(generics.RetrieveAPIView):
    """
    ✅ NEW: Returns lesson detail for Home components (always returns full content)
    """
    permission_classes = [AllowAny]
    serializer_class = LessonDetailSerializer
    queryset = Lesson.objects.filter(is_active=True)

    def retrieve(self, request, *args, **kwargs):
        lesson = self.get_object()
        serializer = self.get_serializer(lesson, context={'request': request})

        return Response({
            **serializer.data,
            'for_home': True  # Flag for home components
        })


class HomeExercisesView(generics.ListAPIView):
    """
    ✅ NEW: Returns exercises data for HomeExercise component
    """
    permission_classes = [AllowAny]
    serializer_class = CourseListSerializer

    def get_queryset(self):
        return Course.objects.filter(is_active=True).order_by('title')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        user = request.user

        courses_with_exercises = []

        for course in queryset:
            # Get lessons with exercises
            lessons_with_exercises = Lesson.objects.filter(
                course=course,
                is_active=True,
                exercise__isnull=False
            ).exclude(exercise={})

            exercises_count = lessons_with_exercises.count()

            if exercises_count > 0:
                # Enrollment status for exercise access
                enrollment_status = 'not_enrolled'
                if user.is_authenticated:
                    enrollment = Enrollment.objects.filter(student=user, course=course).first()
                    enrollment_status = enrollment.status if enrollment else 'not_enrolled'

                course_data = {
                    'id': course.id,
                    'title': course.title,
                    'code': course.code,
                    'description': course.description,
                    'total_exercises': exercises_count,
                    'enrollment_status': enrollment_status,
                    'category': course.get_category_display(),
                    'duration': course.duration,
                    'teacher_name': course.teacher_name,
                    'lessons_with_exercises': LessonListSerializer(
                        lessons_with_exercises,
                        many=True,
                        context={'request': request}
                    ).data
                }
                courses_with_exercises.append(course_data)

        return Response({
            'courses': courses_with_exercises,
            'for_home': True,
            'total_courses_with_exercises': len(courses_with_exercises)
        })


# ✅ RENAME existing methods to correspond to Home components
# Keep the original StudentCourseListView but rename it for clarity
class DashboardCourseListView(generics.ListAPIView):
    """
    ✅ RENAMED: Returns only enrolled courses for dashboard
    Original StudentCourseListView renamed to DashboardCourseListView
    """
    serializer_class = CourseListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Return only enrolled courses for dashboard
        return Course.objects.filter(
            admin_enrollments__student=user,
            admin_enrollments__status__in=['approved', 'completed'],
            is_active=True
        ).distinct().order_by('title')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        user = request.user

        enrolled_courses_data = []

        for course in queryset:
            # Get enrollment status (should always be enrolled for dashboard)
            enrollment = Enrollment.objects.filter(student=user, course=course).first()
            enrollment_status = enrollment.status if enrollment else 'not_enrolled'

            # Get lessons count
            lessons_count = Lesson.objects.filter(course=course, is_active=True).count()

            # Count videos
            video_count = Lesson.objects.filter(
                course=course,
                is_active=True
            ).exclude(
                Q(video_url__isnull=True) |
                Q(video_url='') |
                Q(video_url='null')
            ).count()

            # Count exercises
            exercises_count = 0
            lessons = Lesson.objects.filter(course=course, is_active=True)
            for lesson in lessons:
                if lesson.exercise:
                    exercises_count += 1

            # Calculate progress for enrolled courses
            progress = 0
            if lessons_count > 0:
                completed_lessons = StudentExercise.objects.filter(
                    student=user,
                    lesson__course=course,
                    completed=True
                ).count()
                progress = round((completed_lessons / lessons_count) * 100, 1)

            course_data = {
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'description': course.description,
                'progress': progress,
                'completed_lessons': StudentExercise.objects.filter(
                    student=user,
                    lesson__course=course,
                    completed=True
                ).count(),
                'total_lessons': lessons_count,
                'enrollment_status': enrollment_status,
                'total_exercises': exercises_count,
                'video_count': video_count,
                'category': course.get_category_display(),
                'duration': course.duration,
                'teacher_name': course.teacher_name,
            }

            enrolled_courses_data.append(course_data)

        # Calculate statistics for dashboard
        total_enrollments = Enrollment.objects.filter(student=user).count()
        completed_courses = sum(1 for c in enrolled_courses_data if c['progress'] == 100)

        return Response({
            'courses': enrolled_courses_data,
            'for_dashboard': True,  # Flag for dashboard
            'statistics': {
                'total_courses': len(enrolled_courses_data),
                'total_enrollments': total_enrollments,
                'completed_courses': completed_courses,
                'active_courses': len(enrolled_courses_data) - completed_courses
            }
        })


class DashboardCourseLessonsView(generics.ListAPIView):
    """
    ✅ NEW: Returns lessons only for enrolled courses (dashboard)
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = LessonListSerializer

    def get_queryset(self):
        course_code = self.kwargs.get('course_code')
        user = self.request.user

        # Verify user is enrolled in this course
        enrollment = Enrollment.objects.filter(
            student=user,
            course__code=course_code,
            status__in=['approved', 'completed']
        ).first()

        if not enrollment:
            return Lesson.objects.none()

        return Lesson.objects.filter(
            course__code=course_code,
            course__is_active=True,
            is_active=True
        ).order_by('order')

    def list(self, request, *args, **kwargs):
        course_code = self.kwargs.get('course_code')
        user = request.user

        # Check enrollment
        enrollment = Enrollment.objects.filter(
            student=user,
            course__code=course_code,
            status__in=['approved', 'completed']
        ).first()

        if not enrollment:
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )

        course = get_object_or_404(Course, code=course_code, is_active=True)
        lessons = self.get_queryset()
        serializer = self.get_serializer(lessons, many=True, context={'request': request})

        # Calculate progress for dashboard
        total_lessons = lessons.count()
        completed_lessons = StudentExercise.objects.filter(
            student=user,
            lesson__course=course,
            completed=True
        ).count()

        progress = round((completed_lessons / total_lessons) * 100, 1) if total_lessons > 0 else 0

        return Response({
            'course': {
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'description': course.description,
            },
            'lessons': serializer.data,
            'for_dashboard': True,
            'progress': {
                'total_lessons': total_lessons,
                'completed_lessons': completed_lessons,
                'percentage': progress,
            }
        })

@api_view(['GET'])
@permission_classes([AllowAny])
def guest_course_detail(request, course_code):
    """Get course detail for guest access"""
    session_id = request.GET.get('session_id')
    if not session_id:
        return Response(
            {'detail': 'Session ID required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        session = GuestSession.objects.get(session_id=session_id, is_active=True)
    except GuestSession.DoesNotExist:
        return Response(
            {'detail': 'Invalid session.'},
            status=status.HTTP_404_NOT_FOUND
        )

    if session.is_expired():
        return Response(
            {'detail': 'Session expired.'},
            status=status.HTTP_410_GONE
        )

    course = get_object_or_404(Course, code=course_code, is_active=True)
    settings = GuestAccessSettings.objects.first()

    # Check if course is allowed for guest access
    if settings and not settings.allowed_courses.filter(id=course.id).exists():
        # If no specific courses are set, allow access to any public course
        if not settings.allowed_courses.exists() and course.is_public:
            pass
        else:
            return Response(
                {'detail': 'Course not available for guest access.'},
                status=status.HTTP_403_FORBIDDEN
            )

    #Calculate total exercises
    total_exercises = 0
    lessons = Lesson.objects.filter(course=course, is_active=True)
    for lesson in lessons:
        if lesson.exercise:
            total_exercises += 1

    # Basic course data - NO LEVEL FIELD
    course_data = {
        'id': course.id,
        'title': course.title,
        'description': course.description,
        'code': course.code,
        'duration': course.duration,
        'category': course.display_category,  # Use display_category instead of level
        'teacher_name': course.teacher_name,
        'lessons_count': course.total_lessons,
        'total_exercises': total_exercises,
        'level': 'Beginner',
        'is_public': course.is_public,
    }

    return Response(course_data)


@api_view(['GET'])
@permission_classes([AllowAny])
def guest_lesson_detail_by_slug(request, course_slug, lesson_slug):
    """
    ✅ NEW: Get lesson detail for guest access using slugs instead of IDs
    """
    session_id = request.GET.get('session_id')

    print(f"\n🎯 BACKEND: Processing slug-based guest lesson request")
    print(f"   Course Slug: {course_slug}")
    print(f"   Lesson Slug: {lesson_slug}")
    print(f"   Session ID: {session_id}")

    # ✅ GUEST USER FLOW (not authenticated)
    if not session_id:
        return Response(
            {'detail': 'Session ID required for guest access.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        session = GuestSession.objects.get(session_id=session_id, is_active=True)
        print(f"✅ Session found: {session.session_id}")
    except GuestSession.DoesNotExist:
        print(f"❌ Guest session not found: {session_id}")
        return Response(
            {'detail': 'Invalid or expired guest session.'},
            status=status.HTTP_404_NOT_FOUND
        )

    # ✅ Check if session expired
    if session.is_expired():
        print(f"⏰ Guest session expired: {session_id}")
        session.is_active = False
        session.save()
        return Response(
            {'detail': 'Guest session has expired.'},
            status=status.HTTP_410_GONE
        )

    # ✅ Get course
    try:
        course = get_object_or_404(Course, code=course_slug, is_active=True)
        print(f"✅ Course found: {course.title} ({course.code})")
    except Course.DoesNotExist:
        print(f"❌ Course not found: {course_slug}")
        return Response(
            {'detail': 'Course not found or inactive.'},
            status=status.HTTP_404_NOT_FOUND
        )

    # ✅ Get lesson by slug
    lesson = get_lesson_by_slug(course, lesson_slug)
    if not lesson:
        print(f"❌ Lesson not found by slug: {lesson_slug} in course {course_slug}")
        # Try to find by ID as fallback
        if lesson_slug.isdigit():
            try:
                lesson = Lesson.objects.get(
                    course=course,
                    id=int(lesson_slug),
                    is_active=True
                )
                print(f"✅ Found lesson by ID fallback: {lesson.title}")
            except Lesson.DoesNotExist:
                return Response(
                    {'detail': 'Lesson not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            return Response(
                {'detail': 'Lesson not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

    print(f"✅ Lesson found: {lesson.title} (ID: {lesson.id})")

    settings = GuestAccessSettings.objects.first()

    # ✅ Check if lesson's course is allowed for guest access
    if settings and not settings.allowed_courses.filter(id=lesson.course.id).exists():
        if not settings.allowed_courses.exists() and lesson.course.is_public:
            pass  # Allow if no specific courses set and course is public
        else:
            print(f"🚫 Course {lesson.course.code} not allowed for guest access")
            return Response(
                {'detail': 'This course is not available for guest preview.'},
                status=status.HTTP_403_FORBIDDEN
            )

    # ✅ Check lesson access limit
    accessed_count = session.accessed_lessons.count()
    max_lessons = settings.max_lessons_access if settings else 3

    if accessed_count >= max_lessons and lesson not in session.accessed_lessons.all():
        print(f"⚠️ Guest reached lesson limit: {accessed_count}/{max_lessons}")
        return Response({
            'detail': f'Guest preview limited to {max_lessons} lessons. Please register for full access.',
            'lesson_limit_reached': True,
            'accessed_count': accessed_count,
            'max_lessons': max_lessons
        }, status=status.HTTP_403_FORBIDDEN)

    # ✅ Track accessed lesson (only add if not already tracked)
    if lesson not in session.accessed_lessons.all():
        session.accessed_lessons.add(lesson)
        print(f"📝 Tracked lesson {lesson.id} ({lesson.title}) for guest session {session_id}")

    # Update session time used
    session.time_used += 5  # Add 5 seconds for this request
    session.save()

    # ✅ Parse exercises from lesson.exercise field
    exercises = []
    if lesson.exercise:
        try:
            exercises = parse_exercises_from_lesson(lesson.exercise)
            print(f"✅ Parsed {len(exercises)} exercises for guest lesson {lesson.id}")
        except Exception as e:
            print(f"❌ Error parsing exercises for guest lesson {lesson.id}: {e}")
            exercises = []

    # ✅ Build comprehensive lesson data
    lesson_data = {
        'id': lesson.id,
        'title': lesson.title,
        'description': lesson.description,
        'content': lesson.content,
        'video_url': lesson.video_url,
        'duration': lesson.duration,
        'order': lesson.order,
        'course_title': lesson.course.title,
        'course_code': lesson.course.code,
        'course_id': lesson.course.id,
        'exercises': exercises,
        'completed': False,  # Always false for guests
        'video_completed': False,
        'guest_session': {
            'session_id': str(session.session_id),
            'remaining_time': session.get_remaining_time(),
            'accessed_lessons_count': session.accessed_lessons.count(),
            'max_lessons': max_lessons,
            'time_used': session.time_used,
            'max_session_time': session.max_session_time
        },
        'access_info': {
            'is_guest': True,
            'user_authenticated': False,
            'has_full_access': False,
            'can_complete_lesson': True,
            'can_save_progress': False,
            'prompt_registration': accessed_count >= (max_lessons - 1)
        }
    }

    print(f"✅ Returning guest lesson detail for lesson {lesson.id} ({lesson.title}), session {session_id}")
    return Response(lesson_data)

def extract_exercises_from_text(text):
    """Extract exercises from unstructured text"""
    exercises = []

    # Split by common exercise markers
    markers = ["Question", "Exercise", "Q:", "Q."]

    for marker in markers:
        if marker in text:
            parts = text.split(marker)[1:]  # Skip first part (before first marker)
            for part in parts:
                # Take first 500 chars as exercise content
                exercise_text = part.strip()[:500]
                if exercise_text:
                    exercises.append({
                        "id": len(exercises) + 1,
                        "question": f"{marker}: {exercise_text}",
                        "type": "multiple-choice",
                        "options": ["Option A", "Option B", "Option C", "Option D"],
                        "correct": 0,
                        "explanation": "Sample explanation for guest preview"
                    })

    # If no markers found, create a generic exercise
    if not exercises and text.strip():
        exercises.append({
            "id": 1,
            "question": "Review what you learned in this lesson",
            "type": "paragraph",
            "word_count": {"min": 10},
            "explanation": "Reflect on the key concepts you learned."
        })

    return exercises

def clean_exercises(exercises):
    """Clean and validate exercise data"""
    cleaned = []

    for i, ex in enumerate(exercises):
        if not isinstance(ex, dict):
            continue

        # Ensure required fields
        exercise_id = ex.get("id") or i + 1
        question = ex.get("question") or ex.get("text") or "Question " + str(i + 1)
        ex_type = ex.get("type") or "multiple-choice"

        # Build cleaned exercise
        cleaned_ex = {
            "id": exercise_id,
            "question": question,
            "type": ex_type,
            "correct": ex.get("correct") or 0,
            "explanation": ex.get("explanation") or "Review the lesson content for the correct answer."
        }

        # Add type-specific fields
        if ex_type in ["multiple-choice", "true-false"]:
            cleaned_ex["options"] = ex.get("options") or ["Option A", "Option B", "Option C", "Option D"]
        elif ex_type == "fill-blank":
            cleaned_ex["correct"] = ex.get("correct") or "answer"
        elif ex_type == "paragraph":
            cleaned_ex["word_count"] = ex.get("word_count") or {"min": 10}

        cleaned.append(cleaned_ex)

    return cleaned

@api_view(['GET'])
@permission_classes([AllowAny])
def guest_course_lessons(request, course_code):
    """
    ✅ FIXED: Get lessons for a course with video indicators AND slugs
    """
    session_id = request.GET.get('session_id')

    try:
        course = Course.objects.get(code=course_code, is_active=True)
        settings = GuestAccessSettings.objects.first()

        # Get lessons (apply guest limit)
        max_lessons = settings.max_lessons_access if settings else 3
        lessons = course.lessons.filter(is_active=True).order_by('order')[:max_lessons]

        lesson_data = []
        for lesson in lessons:
            # ✅ Count exercises properly
            exercise_count = 0
            if lesson.exercise:
                if isinstance(lesson.exercise, list):
                    exercise_count = len(lesson.exercise)
                elif isinstance(lesson.exercise, dict):
                    if 'questions' in lesson.exercise:
                        exercise_count = len(lesson.exercise.get('questions', []))
                    else:
                        exercise_types = ['multiple_choice', 'fill_blank', 'paragraph', 'true_false']
                        exercise_count = sum(1 for ex_type in exercise_types if ex_type in lesson.exercise)
                        if exercise_count == 0:
                            exercise_count = 1

            # ✅ Check for video
            has_video = bool(
                lesson.video_url and
                isinstance(lesson.video_url, str) and
                lesson.video_url.strip() != '' and
                lesson.video_url != 'null'
            )

            # ✅ Generate slug for frontend navigation
            lesson_slug = generate_slug(lesson.title)

            lesson_data.append({
                'id': lesson.id,
                'title': lesson.title,
                'description': lesson.description,
                'duration': lesson.duration,
                'order': lesson.order,
                'course_title': course.title,
                'course_code': course.code,
                'exercise_count': exercise_count,
                'completed': False,
                'has_video': has_video,
                'video_url': lesson.video_url if has_video else None,
                'slug': lesson_slug,  # ✅ ADD THIS: Include slug for frontend navigation
            })

        print(f"✅ Returning {len(lesson_data)} lessons for {course_code}")
        print(f"   Videos found: {sum(1 for l in lesson_data if l['has_video'])}")

        return Response(lesson_data)

    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        print(f"❌ Error in guest_course_lessons: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response([], status=status.HTTP_200_OK)

def parse_exercises_from_lesson(exercise_data):
    """
    Convert the database exercise format to frontend expected format
    Database format: Dict with keys 'paragraph', 'fill_blank', 'multiple_choice'
    Frontend format: Array of exercise objects with 'type', 'question', etc.
    """
    print(f"🔧 PARSING EXERCISE DATA: Type={type(exercise_data)}")

    if not exercise_data:
        print("❌ No exercise data provided")
        return []

    exercises = []
    exercise_id_counter = 1

    try:
        # CASE 1: Already a list (already converted)
        if isinstance(exercise_data, list):
            print(f"✅ Exercise data is already a list with {len(exercise_data)} items")
            return exercise_data

        # CASE 2: Dictionary with exercise types as keys (YOUR DATABASE FORMAT)
        elif isinstance(exercise_data, dict):
            print(f"📊 Processing dictionary with keys: {list(exercise_data.keys())}")

            # Process paragraph exercise
            if 'paragraph' in exercise_data:
                paragraph_data = exercise_data['paragraph']
                print(f"📝 Found paragraph exercise: {paragraph_data.get('prompt', '')[:50]}...")

                exercises.append({
                    'id': exercise_id_counter,
                    'type': 'paragraph',
                    'question': paragraph_data.get('prompt', 'Write about what you learned.'),
                    'word_count': paragraph_data.get('word_count', {'min': 50, 'max': 300}),
                    'explanation': paragraph_data.get('guidelines', '')
                })
                exercise_id_counter += 1

            # Process fill_blank exercise
            if 'fill_blank' in exercise_data:
                fill_data = exercise_data['fill_blank']
                print(f"📝 Found fill_blank exercise: {fill_data.get('text', '')[:50]}...")

                # Extract the blank from text (text like "The number drie represents __________.")
                text = fill_data.get('text', '')
                question = text
                correct_answer = fill_data.get('answers', [''])[0] if fill_data.get('answers') else ''

                exercises.append({
                    'id': exercise_id_counter,
                    'type': 'fill-blank',  # Frontend expects 'fill-blank' with hyphen
                    'question': question,
                    'correct': correct_answer,
                    'explanation': fill_data.get('explanation', '')
                })
                exercise_id_counter += 1

            # Process multiple_choice exercise
            if 'multiple_choice' in exercise_data:
                mc_data = exercise_data['multiple_choice']
                print(f"📝 Found multiple_choice exercise: {mc_data.get('question', '')[:50]}...")

                exercises.append({
                    'id': exercise_id_counter,
                    'type': 'multiple-choice',
                    'question': mc_data.get('question', 'Choose the correct answer.'),
                    'options': mc_data.get('options', ['Option A', 'Option B', 'Option C', 'Option D']),
                    'correct': mc_data.get('correct_answer', 0),  # 0-based index for frontend
                    'explanation': mc_data.get('explanation', '')
                })
                exercise_id_counter += 1

            # Process true_false if it exists
            if 'true_false' in exercise_data:
                tf_data = exercise_data['true_false']
                question = tf_data.get('question', 'True or False?')
                correct = tf_data.get('correct', True)

                exercises.append({
                    'id': exercise_id_counter,
                    'type': 'true-false',
                    'question': question,
                    'options': ['True', 'False'],
                    'correct': 0 if correct else 1,  # 0 for True, 1 for False
                    'explanation': tf_data.get('explanation', '')
                })
                exercise_id_counter += 1

            print(f"✅ Converted {len(exercises)} exercises from dictionary format")
            return exercises

        # CASE 3: String that might be JSON
        elif isinstance(exercise_data, str):
            try:
                # Try to parse as JSON
                parsed = json.loads(exercise_data)
                # Recursively parse
                return parse_exercises_from_lesson(parsed)
            except json.JSONDecodeError:
                print(f"❌ Could not parse string as JSON")
                return []

        else:
            print(f"⚠️ Unknown exercise data type: {type(exercise_data)}")
            return []

    except Exception as e:
        print(f"❌ Error parsing exercises: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

def format_exercise_by_type(ex_data, ex_type, index):
    """Format exercise based on type"""
    exercise = {
        'id': str(ex_data.get('id', f'question_{index}')),
        'type': ex_type.replace('_', '-'),
        'explanation': ex_data.get('explanation', ''),
    }

    if ex_type == 'multiple_choice':
        exercise['question'] = ex_data.get('question', '')
        exercise['options'] = ex_data.get('options', [])
        exercise['correct'] = ex_data.get('correct_answer', ex_data.get('correct', 0))

    elif ex_type == 'fill_blank':
        exercise['question'] = ex_data.get('text', ex_data.get('question', ''))
        exercise['options'] = []

        if 'answers' in ex_data and ex_data['answers']:
            exercise['correct'] = ex_data['answers'][0]
        elif 'answer' in ex_data:
            exercise['correct'] = ex_data['answer']
        else:
            exercise['correct'] = ''

    elif ex_type == 'true_false':
        exercise['question'] = ex_data.get('question', '')
        exercise['options'] = ['True', 'False']
        correct_val = ex_data.get('correct_answer', True)
        exercise['correct'] = 0 if correct_val else 1

    elif ex_type == 'paragraph':
        exercise['question'] = ex_data.get('prompt', ex_data.get('question', ''))
        exercise['options'] = []
        exercise['correct'] = None
        exercise['word_count'] = {
            'min': ex_data.get('word_count', {}).get('min', 1),
            'max': 3000
        }

    return exercise

def format_exercise(ex, index):
    """Format individual exercise when exercises are in a list"""
    if not isinstance(ex, dict):
        return None

    exercise_type = ex.get('type', 'multiple-choice')

    if exercise_type in ['fill-blank', 'fill_blank']:
        question_text = ex.get('text', ex.get('question', ''))
        if 'answers' in ex and ex['answers']:
            correct_answer = ex['answers'][0]
        elif 'answer' in ex:
            correct_answer = ex['answer']
        else:
            correct_answer = ''

    elif exercise_type == 'paragraph':
        question_text = ex.get('prompt', ex.get('question', ''))
        correct_answer = None

    else:
        question_text = ex.get('question', ex.get('prompt', ''))
        correct_answer = ex.get('correct', ex.get('correct_answer', 0))

    return {
        'id': str(ex.get('id', f'question_{index}')),
        'type': exercise_type,
        'question': question_text,
        'options': ex.get('options', []),
        'correct': correct_answer,
        'explanation': ex.get('explanation', ''),
        'word_count': ex.get('word_count', {'min': 1, 'max': 3000}) if exercise_type == 'paragraph' else None
    }

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_lesson_detail(request, lesson_id):
    """
    ✅ UPDATED: Get lesson detail for authenticated students - Properly integrated
    Uses Django REST Framework and matches frontend expectations
    """
    print(f"=== STUDENT LESSON DETAIL REQUEST ===")
    print(f"Lesson ID: {lesson_id}")
    print(f"User: {request.user.email}")
    print(f"Authenticated: {request.user.is_authenticated}")

    if not request.user.is_authenticated:
        return Response(
            {'detail': 'Authentication required.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    try:
        # Get the lesson with related course
        lesson = get_object_or_404(
            Lesson.objects.select_related('course'),
            id=lesson_id,
            is_active=True
        )

        print(f"Found lesson: {lesson.title}")
        print(f"Course: {lesson.course.title} ({lesson.course.code})")

        # Check enrollment with correct status values
        is_enrolled = Enrollment.objects.filter(
            student=request.user,
            course=lesson.course,
            status__in=['approved', 'completed', 'enrolled']  # ✅ Use correct status values
        ).exists()

        print(f"User enrolled: {is_enrolled}")

        if not is_enrolled:
            return Response({
                'detail': 'You are not enrolled in this course.',
                'course_code': lesson.course.code,
                'course_title': lesson.course.title,
                'enrollment_required': True
            }, status=status.HTTP_403_FORBIDDEN)

        # Get student exercise record
        student_exercise = StudentExercise.objects.filter(
            student=request.user,
            lesson=lesson
        ).first()

        # Get video progress
        from admin_dashboard.models import LessonProgress
        video_progress = LessonProgress.objects.filter(
            student=request.user,
            lesson=lesson
        ).first()

        # Parse exercises from lesson.exercise field
        exercises = []
        if lesson.exercise:
            try:
                exercises = parse_exercises_from_lesson(lesson.exercise)
                print(f"Parsed {len(exercises)} exercises")
            except Exception as e:
                print(f"Error parsing exercises for lesson {lesson_id}: {e}")
                exercises = []
        else:
            print("No exercises in this lesson")

        # Check completion status
        completed = False
        video_completed = False

        if student_exercise:
            completed = student_exercise.completed
            print(f"Student exercise found: completed={completed}, score={student_exercise.score}")
        else:
            print("No student exercise record found")

        if video_progress:
            video_completed = video_progress.video_completed
            print(f"Video progress: completed={video_completed}, progress={video_progress.video_progress}")
        else:
            print("No video progress record found")

        # Get teacher info
        teacher_info = None
        if lesson.course.teacher and lesson.course.teacher.user:
            teacher_info = {
                'id': lesson.course.teacher.id,
                'name': f"{lesson.course.teacher.user.first_name} {lesson.course.teacher.user.last_name}".strip(),
                'email': lesson.course.teacher.user.email,
                'bio': getattr(lesson.course.teacher, 'bio', '')
            }

        # Build comprehensive lesson data
        lesson_data = {
            'id': lesson.id,
            'title': lesson.title,
            'description': lesson.description or '',
            'content': lesson.content or '',
            'video_url': lesson.video_url,
            'duration': lesson.duration or 30,
            'order': lesson.order or 0,
            'created_at': lesson.created_at.isoformat() if lesson.created_at else None,
            'updated_at': lesson.updated_at.isoformat() if lesson.updated_at else None,

            # Course info
            'course_id': lesson.course.id,
            'course_title': lesson.course.title,
            'course_code': lesson.course.code,
            'course_description': lesson.course.description,

            # Exercises
            'exercises': exercises,
            'exercise_count': len(exercises),

            # Completion status
            'completed': completed,
            'video_completed': video_completed,
            'completed_at': student_exercise.completed_at.isoformat() if student_exercise and student_exercise.completed_at else None,

            # Student progress
            'student_progress': {
                'exercise_score': float(student_exercise.score) if student_exercise and student_exercise.score else 0.0,
                'completed_at': student_exercise.completed_at.isoformat() if student_exercise and student_exercise.completed_at else None,
                'video_progress': video_progress.video_progress if video_progress else 0,
                'video_completed': video_completed,
                'submission_data': student_exercise.submission_data if student_exercise else {}
            },

            # Teacher info
            'teacher': teacher_info,
            'teacher_name': teacher_info['name'] if teacher_info else lesson.course.teacher_name,

            # Access info
            'access_info': {
                'is_guest': False,
                'user_authenticated': True,
                'has_full_access': True,
                'can_complete_lesson': True,
                'can_save_progress': True,
                'user_type': request.user.profile.user_type if hasattr(request.user, 'profile') else 'student',
                'enrollment_status': 'approved'
            },

            # Navigation
            'has_previous': False,  # Will be calculated if needed
            'has_next': False,      # Will be calculated if needed
        }

        print(f"✅ Returning student lesson detail for user {request.user.id}")
        print(f"Lesson data keys: {lesson_data.keys()}")
        print(f"Exercises count: {len(lesson_data['exercises'])}")

        return Response(lesson_data, status=status.HTTP_200_OK)

    except Lesson.DoesNotExist:
        print(f"❌ Lesson not found: {lesson_id}")
        return Response(
            {'detail': 'Lesson not found or inactive.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        print(f"❌ Error in student_lesson_detail: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response(
            {'detail': f'Failed to load lesson: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# Add a helper function to handle guest-to-student transition
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def transfer_guest_progress(request):
    """
    Transfer guest progress to authenticated user account
    Called when a guest registers/logs in and wants to keep their progress
    """
    try:
        guest_session_id = request.data.get('guest_session_id')
        course_slug = request.data.get('course_slug')

        if not guest_session_id:
            return Response(
                {'detail': 'Guest session ID required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get guest session
        try:
            guest_session = GuestSession.objects.get(session_id=guest_session_id)
        except GuestSession.DoesNotExist:
            return Response(
                {'detail': 'Guest session not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get course
        try:
            course = Course.objects.get(code=course_slug)
        except Course.DoesNotExist:
            return Response(
                {'detail': 'Course not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Check enrollment
        enrollment, created = Enrollment.objects.get_or_create(
            student=request.user,
            course=course,
            defaults={'status': 'enrolled'}
        )

        # Get lessons accessed in guest session
        guest_lessons = guest_session.accessed_lessons.filter(course=course)

        transferred_count = 0
        for lesson in guest_lessons:
            # Create student exercise record if not exists
            student_exercise, created = StudentExercise.objects.get_or_create(
                student=request.user,
                lesson=lesson,
                defaults={
                    'completed': True,  # Mark as completed since guest "completed" them
                    'score': 100,  # Assume perfect score for guest completion
                    'video_completed': True
                }
            )

            if created:
                transferred_count += 1

        # Mark guest session as transferred
        guest_session.is_active = False
        guest_session.save()

        return Response({
            'success': True,
            'message': f'Successfully transferred {transferred_count} lesson completions to your account.',
            'transferred_count': transferred_count,
            'course_code': course.code,
            'enrollment_status': enrollment.status
        })

    except Exception as e:
        print(f"❌ Error transferring guest progress: {e}")
        return Response(
            {'detail': 'Failed to transfer guest progress.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([AllowAny])
def guest_submit_exercise(request, lesson_id, exercise_id):
    """Submit exercise answer for guest user"""
    session_id = request.data.get('session_id')
    if not session_id:
        return Response(
            {'detail': 'Session ID required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        session = GuestSession.objects.get(session_id=session_id, is_active=True)
    except GuestSession.DoesNotExist:
        return Response(
            {'detail': 'Invalid session.'},
            status=status.HTTP_404_NOT_FOUND
        )

    if session.is_expired():
        return Response(
            {'detail': 'Session expired.'},
            status=status.HTTP_410_GONE
        )

    # For guest users, simulate exercise submission
    answer = request.data.get('answer')

    return Response({
        'detail': 'Exercise submitted successfully (guest mode)',
        'is_correct': True,  # Always return true for guest mode
        'explanation': 'This is a preview. Your progress will not be saved.',
        'guest_mode': True
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def public_courses_list(request):
    """Get list of courses available for public viewing - NO AUTH REQUIRED"""
    try:
        courses = Course.objects.filter(
            is_active=True,
            is_public=True
        ).select_related('teacher__user')[:12]

        course_data = []
        for course in courses:
            course_data.append({
                'id': course.id,
                'title': course.title,
                'description': course.description,
                'code': course.code,
                'duration': course.duration,
                'category': course.display_category,  # Use display_category instead of level
                'price': getattr(course, 'price', 0),
                'lessons_count': course.lessons.filter(is_active=True).count(),
                'is_popular': getattr(course, 'is_popular', False),
                'is_new': getattr(course, 'is_new', False),
                'teacher_name': course.teacher_name,
            })

        return Response(course_data)
    except Exception as e:
        print(f"Public courses error: {str(e)}")
        return Response([], status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Simple health check endpoint"""
    return Response({
        'status': 'healthy',
        'timestamp': timezone.now().isoformat(),
        'service': 'Dreams Academy Backend'
    })

@api_view(['GET'])
@permission_classes([AllowAny])
def debug_guest_courses(request):
    """Debug endpoint to see exact course data structure"""
    from accounts.models import Course
    from student_dashboard.models import GuestAccessSettings

    settings = GuestAccessSettings.objects.first()
    courses = Course.objects.filter(is_active=True).order_by('title')[:5]  # Just first 5 for testing

    debug_data = []
    for course in courses:
        debug_data.append({
            'id': course.id,
            'title': course.title,
            'code': course.code,
            'description': course.description[:100] + '...' if course.description else '',
            'duration': course.duration,
            'price': float(course.price),
            'is_active': course.is_active,
            'lessons_count': course.lessons.filter(is_active=True).count(),
            'teacher': str(course.teacher) if course.teacher else None,
            'has_level': hasattr(course, 'level'),
            'level_value': getattr(course, 'level', 'NOT_SET'),
        })

    return Response({
        'total_courses': Course.objects.filter(is_active=True).count(),
        'guest_settings': {
            'enabled': settings.enabled if settings else False,
            'allowed_courses': settings.allowed_courses.count() if settings else 0,
        },
        'sample_courses': debug_data,
        'message': 'This is for debugging the course data structure'
    })

class GuestCourseDetailView(generics.RetrieveAPIView):
    """
    API endpoint for guests to view individual course details
    """
    permission_classes = [AllowAny]
    lookup_field = 'code'
    lookup_url_kwarg = 'course_code'

    def get_queryset(self):
        return Course.objects.filter(is_active=True)

    def retrieve(self, request, *args, **kwargs):
        course = self.get_object()

        # Get guest session if available
        session_id = request.query_params.get('session_id')

        # Basic course data for guests - NO LEVEL
        course_data = {
            'id': course.id,
            'title': course.title,
            'description': course.description,
            'code': course.code,
            'duration': course.duration,
            'category': course.display_category,  # Use display_category instead of level
            'price': float(course.price),
            'is_active': course.is_active,
            'created_at': course.created_at.isoformat() if course.created_at else None,
            'teacher_name': course.teacher_name,
            'total_lessons': course.total_lessons,
            'enrollment_status': 'guest_preview',
            'progress': 0,
            'completed_lessons': 0,
        }

        # Get lessons for this course (limited preview)
        lessons = course.lessons.filter(is_active=True).order_by('order')

        # Apply guest access limits
        settings = GuestAccessSettings.objects.first()
        max_lessons = settings.max_lessons_access if settings else 3

        preview_lessons = lessons[:max_lessons]

        # Serialize lessons
        lesson_data = []
        for lesson in preview_lessons:
            lesson_data.append({
                'id': lesson.id,
                'title': lesson.title,
                'description': lesson.description,
                'duration': lesson.duration,
                'order': lesson.order,
                'is_active': lesson.is_active,
                'created_at': lesson.created_at.isoformat() if lesson.created_at else None,
                'completed': False,  # Always false for guests
                'exercise_count': 1 if lesson.exercise else 0,
            })

        course_data['lessons'] = lesson_data

        return Response(course_data)
class GuestCourseLessonsView(generics.ListAPIView):
    """
    API endpoint for guests to view course lessons
    """
    permission_classes = [AllowAny]

    def get_queryset(self):
        course_code = self.kwargs.get('course_code')
        return Lesson.objects.filter(
            course__code=course_code,
            course__is_active=True,
            is_active=True
        ).order_by('order')

    def list(self, request, *args, **kwargs):
        course_code = self.kwargs.get('course_code')
        course = get_object_or_404(Course, code=course_code, is_active=True)

        # Apply guest access limits
        settings = GuestAccessSettings.objects.first()
        max_lessons = settings.max_lessons_access if settings else 3

        lessons = self.get_queryset()[:max_lessons]

        # Serialize lessons
        lesson_data = []
        for lesson in lessons:
            lesson_data.append({
                'id': lesson.id,
                'title': lesson.title,
                'description': lesson.description,
                'duration': lesson.duration,
                'order': lesson.order,
                'is_active': lesson.is_active,
                'course_title': course.title,
                'course_code': course.code,
                'completed': False,
                'exercise_count': 1 if lesson.exercise else 0,
            })

        return Response(lesson_data)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def enroll_in_course(request, course_code):
    """
    ✅ ENHANCED: Enrollment with proper status tracking and responses
    """
    try:
        course = get_object_or_404(Course, code=course_code, is_active=True)
        user = request.user

        print(f"\n🎯 ENROLLMENT REQUEST:")
        print(f"   User: {user.email}")

        # Get user profile and type
        try:
            user_profile = user.user_profile
            user_type = user_profile.user_type
            print(f"   User Type: {user_type}")
        except UserProfile.DoesNotExist:
            # Create profile if it doesn't exist
            user_profile = UserProfile.objects.create(
                user=user,
                user_type='student',  # Default to student
                terms_agreed=True
            )
            user_type = 'student'
            print(f"   Created missing profile with type: {user_type}")

        # Check user role
        if user_type in ['admin', 'teacher']:
            return Response(
                {
                    'detail': f'You cannot enroll as a {user_type}. You are the course creator!',
                    'error_code': 'INVALID_USER_ROLE'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # Check if already enrolled
        existing_enrollment = Enrollment.objects.filter(
            student=user,
            course=course
        ).first()

        if existing_enrollment:
            status_display = existing_enrollment.status
            if existing_enrollment.status == 'approved':
                return Response(
                    {
                        'detail': f'You are already enrolled in "{course.title}".',
                        'enrollment_status': status_display,
                        'enrolled_at': existing_enrollment.enrolled_at,
                        'course': {
                            'id': course.id,
                            'title': course.title,
                            'code': course.code
                        }
                    },
                    status=status.HTTP_200_OK
                )
            else:
                return Response(
                    {
                        'detail': f'Your enrollment in "{course.title}" is {status_display}.',
                        'enrollment_status': status_display,
                        'enrolled_at': existing_enrollment.enrolled_at,
                        'course': {
                            'id': course.id,
                            'title': course.title,
                            'code': course.code
                        }
                    },
                    status=status.HTTP_200_OK
                )

        # Create new enrollment - auto-approve for students
        enrollment = Enrollment.objects.create(
            student=user,
            course=course,
            status='approved'  # Auto-approve enrollment for students
        )

        print(f"✅ New enrollment created: {enrollment.id}")
        print(f"   Course: {course.title}")
        print(f"   Status: {enrollment.status}")

        return Response({
            'detail': f'Successfully enrolled in "{course.title}"!',
            'enrollment_status': enrollment.status,
            'enrolled_at': enrollment.enrolled_at,
            'course': {
                'id': course.id,
                'title': course.title,
                'code': course.code
            }
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        print(f"❌ Enrollment error: {str(e)}")
        import traceback
        traceback.print_exc()

        return Response(
            {
                'detail': f'Error during enrollment: {str(e)}',
                'error_code': 'ENROLLMENT_ERROR'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([AllowAny])
def debug_courses(request):
    """Debug endpoint to check course data"""
    courses = Course.objects.filter(is_active=True)[:5]

    debug_data = []
    for course in courses:
        debug_data.append({
            'id': course.id,
            'title': course.title,
            'code': course.code,
            'has_level_field': hasattr(course, 'level'),
            'category': course.category,
            'display_category': course.display_category,
            'is_popular': course.is_popular,
            'is_new': course.is_new,
        })

    return Response({
        'total_courses': Course.objects.filter(is_active=True).count(),
        'sample_courses': debug_data,
        'message': 'Debug course data'
    })


# Add to student_dashboard/views.py

class CertificateSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)
    category = serializers.CharField(source='course.display_category', read_only=True)
    issue_date = serializers.SerializerMethodField()
    formatted_grade = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = [
            'id', 'certificate_id', 'course_title', 'course_code',
            'issued_date', 'issue_date', 'grade', 'formatted_grade',
            'download_url', 'category'
        ]

    def get_issue_date(self, obj):
        return obj.issued_date.strftime('%B %d, %Y')

    def get_formatted_grade(self, obj):
        return f"{obj.grade}%"
@api_view(['GET'])
@permission_classes([AllowAny])
def student_certificates_list(request):
    """
    ✅ ALL users (guests and authenticated) can see certificates list
    For guests: Show available courses with signup prompts
    For authenticated: Show their actual enrolled courses with completion status
    """
    user = request.user

    try:
        # Get all active courses from the database
        all_courses = Course.objects.filter(is_active=True).order_by('title')

        print(f"🔍 Loading certificates data from {all_courses.count()} real courses")

        certificates_data = []

        for course in all_courses:
            try:
                # For all users, get basic course info
                course_data = {
                    'id': course.id,
                    'course_title': course.title,
                    'course_code': course.code,
                    'category': course.category,
                    'teacher_name': course.teacher_name,
                    'total_lessons': course.lessons.filter(is_active=True).count(),
                    'description': course.description,
                }

                # For authenticated users, add progress and completion status
                if user.is_authenticated:
                    # Calculate progress for this course
                    total_lessons = Lesson.objects.filter(course=course, is_active=True).count()
                    completed_lessons = StudentExercise.objects.filter(
                        student=user,
                        lesson__course=course,
                        completed=True
                    ).count()

                    progress = round((completed_lessons / total_lessons) * 100, 1) if total_lessons > 0 else 0
                    is_completed = progress >= 100

                    # Check if user is enrolled
                    is_enrolled = Enrollment.objects.filter(
                        student=user,
                        course=course,
                        status__in=['approved', 'completed']
                    ).exists()

                    # Check if certificate exists in database
                    certificate_exists = False
                    existing_certificate = None

                    try:
                        existing_certificate = Certificate.objects.filter(
                            user=user,
                            course=course,
                            is_active=True
                        ).first()
                        certificate_exists = existing_certificate is not None
                    except Exception as cert_error:
                        print(f"⚠️ Certificate query error for course {course.code}: {cert_error}")
                        certificate_exists = False

                    if certificate_exists and existing_certificate:
                        # Use real certificate data
                        certificate_data = {
                            **course_data,
                            'certificate_id': str(existing_certificate.certificate_id),
                            'issue_date': existing_certificate.issued_date.strftime('%B %d, %Y'),
                            'formatted_grade': f"{existing_certificate.grade}%",
                            'download_url': existing_certificate.download_url,
                            'is_valid': existing_certificate.is_valid,
                            'accessible': existing_certificate.is_valid,
                            'message': 'Certificate available for download' if existing_certificate.is_valid else 'Complete the course to access this certificate',
                            'progress': progress,
                            'is_enrolled': is_enrolled,
                            'is_real_certificate': True
                        }
                    else:
                        # Create certificate data based on course progress
                        certificate_data = {
                            **course_data,
                            'certificate_id': f'course-{course.code}-{user.id}',
                            'issue_date': 'In Progress' if not is_completed else timezone.now().strftime('%B %d, %Y'),
                            'formatted_grade': f'{progress}%',
                            'download_url': f'/api/student/courses/{course.code}/generate-certificate/' if is_completed else None,
                            'is_valid': is_completed,
                            'accessible': is_completed and is_enrolled,
                            'message': 'Course completed! Click to generate certificate.' if is_completed else
                                      f'Progress: {progress}% - Complete all lessons to earn certificate' if is_enrolled else
                                      'Enroll in this course to earn a certificate',
                            'progress': progress,
                            'is_enrolled': is_enrolled,
                            'is_real_certificate': False
                        }

                else:
                    # For guests, show course with signup prompt
                    certificate_data = {
                        **course_data,
                        'certificate_id': f'guest-{course.code}',
                        'issue_date': 'Available upon completion',
                        'formatted_grade': '0%',
                        'download_url': None,
                        'is_valid': False,
                        'accessible': False,
                        'message': 'Sign up and complete this course to earn a certificate',
                        'progress': 0,
                        'is_enrolled': False,
                        'is_real_certificate': False
                    }

                certificates_data.append(certificate_data)
                print(f"✅ Added certificate data for course: {course.title}")

            except Exception as course_error:
                print(f"❌ Error processing course {course.code}: {course_error}")
                continue

        print(f"🎓 Final certificates data: {len(certificates_data)} items for user: {user.email if user.is_authenticated else 'guest'}")

        return Response({
            'certificates': certificates_data,
            'total_certificates': len(certificates_data),
            'user_type': 'authenticated' if user.is_authenticated else 'guest',
            'total_courses': all_courses.count()
        })

    except Exception as e:
        print(f"❌ Error fetching certificates: {e}")
        import traceback
        traceback.print_exc()

        return Response({
            'detail': 'Failed to load certificates.',
            'certificates': [],
            'total_certificates': 0
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])  # Only authenticated users
def download_certificate(request, certificate_id):
    """
    ✅ Download certificate - ONLY for authenticated users with completed courses
    """
    user = request.user

    try:
        # Check if it's a sample certificate ID
        if certificate_id.startswith('sample-'):
            course_code = certificate_id.replace('sample-', '')
            course = get_object_or_404(Course, code=course_code, is_active=True)

            # Check if course is completed
            total_lessons = Lesson.objects.filter(course=course, is_active=True).count()
            completed_lessons = StudentExercise.objects.filter(
                student=user,
                lesson__course=course,
                completed=True
            ).count()

            if completed_lessons < total_lessons:
                return Response(
                    {'detail': 'Course not completed. Cannot generate certificate.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Generate certificate on the fly
            return Response({
                'detail': 'Certificate generated successfully!',
                'download_url': f'/api/student/courses/{course_code}/generate-certificate/',
                'course_title': course.title,
                'issued_date': timezone.now().strftime('%B %d, %Y'),
                'message': 'This is a preview. In production, a PDF would be generated.'
            })

        # Handle real certificate from database
        certificate = get_object_or_404(
            Certificate,
            certificate_id=certificate_id,
            user=user,
            is_active=True
        )

        if not certificate.is_valid:
            return Response(
                {'detail': 'Certificate not available. Course not completed.'},
                status=status.HTTP_403_FORBIDDEN
            )

        return Response({
            'detail': 'Certificate download started!',
            'download_url': certificate.download_url or certificate.generate_certificate(),
            'certificate_id': str(certificate.certificate_id),
            'course_title': certificate.course.title,
            'issued_date': certificate.issued_date.strftime('%B %d, %Y')
        })

    except Certificate.DoesNotExist:
        return Response(
            {'detail': 'Certificate not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        print(f"❌ Certificate download error: {e}")
        return Response(
            {'detail': 'Failed to download certificate.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])  # Only authenticated users
def view_certificate(request, certificate_id):
    """
    ✅ View certificate - ONLY for authenticated users with completed courses
    """
    user = request.user

    try:
        if certificate_id.startswith('sample-'):
            course_code = certificate_id.replace('sample-', '')
            course = get_object_or_404(Course, code=course_code, is_active=True)

            # Check if course is completed
            total_lessons = Lesson.objects.filter(course=course, is_active=True).count()
            completed_lessons = StudentExercise.objects.filter(
                student=user,
                lesson__course=course,
                completed=True
            ).count()

            if completed_lessons < total_lessons:
                return Response(
                    {'detail': 'Complete the course to view certificate.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            return Response({
                'viewable': True,
                'course_title': course.title,
                'course_code': course.code,
                'issued_date': timezone.now().strftime('%B %d, %Y'),
                'grade': '100%',
                'full_name': f"{user.first_name} {user.last_name}".strip() or user.email,
                'message': 'Certificate Preview - Course Completed!'
            })

        certificate = get_object_or_404(
            Certificate,
            certificate_id=certificate_id,
            user=user,
            is_active=True
        )

        if not certificate.is_valid:
            return Response(
                {'detail': 'Certificate not available. Course not completed.'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CertificateSerializer(certificate)

        return Response({
            **serializer.data,
            'viewable': True,
            'full_name': f"{user.first_name} {user.last_name}".strip() or user.email
        })

    except Certificate.DoesNotExist:
        return Response(
            {'detail': 'Certificate not found.'},
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def generate_certificate(request, course_code):
    """
    ✅ Generate certificate when course is completed
    This would typically be called automatically when course completion is detected
    """
    user = request.user
    course = get_object_or_404(Course, code=course_code, is_active=True)

    try:
        # Check if course is completed
        from admin_dashboard.models import Enrollment
        from .models import StudentExercise

        enrollment = Enrollment.objects.filter(
            student=user,
            course=course,
            status='completed'
        ).first()

        if not enrollment:
            return Response(
                {'detail': 'Course not completed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if all lessons are completed
        total_lessons = Lesson.objects.filter(course=course, is_active=True).count()
        completed_lessons = StudentExercise.objects.filter(
            student=user,
            lesson__course=course,
            completed=True
        ).count()

        if completed_lessons < total_lessons:
            return Response(
                {'detail': 'Not all lessons completed.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Calculate final grade (average of all lesson scores)
        lesson_scores = StudentExercise.objects.filter(
            student=user,
            lesson__course=course,
            completed=True
        ).values_list('score', flat=True)

        if lesson_scores:
            average_grade = sum(lesson_scores) / len(lesson_scores) * 100
        else:
            average_grade = 100.0  # Default if no scores

        # Create or update certificate
        certificate, created = Certificate.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                'grade': average_grade,
                'download_url': None
            }
        )

        if not created:
            certificate.grade = average_grade
            certificate.save()

        # Generate download URL
        if not certificate.download_url:
            certificate.download_url = certificate.generate_certificate()
            certificate.save()

        serializer = CertificateSerializer(certificate)

        return Response({
            'detail': 'Certificate generated successfully.' if created else 'Certificate updated.',
            'certificate': serializer.data
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    except Exception as e:
        print(f"❌ Certificate generation error: {e}")
        return Response(
            {'detail': 'Failed to generate certificate.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def check_certificate_eligibility(request, course_code):
    """
    ✅ Check if user is eligible for certificate for a course
    """
    user = request.user
    course = get_object_or_404(Course, code=course_code, is_active=True)

    try:
        from admin_dashboard.models import Enrollment
        from .models import StudentExercise

        # Check enrollment
        enrollment = Enrollment.objects.filter(
            student=user,
            course=course
        ).first()

        if not enrollment or enrollment.status != 'completed':
            return Response({
                'eligible': False,
                'reason': 'Course not completed',
                'progress': 0
            })

        # Calculate progress
        total_lessons = Lesson.objects.filter(course=course, is_active=True).count()
        completed_lessons = StudentExercise.objects.filter(
            student=user,
            lesson__course=course,
            completed=True
        ).count()

        progress = (completed_lessons / total_lessons * 100) if total_lessons > 0 else 0

        eligible = completed_lessons >= total_lessons

        # Check if certificate already exists
        existing_certificate = Certificate.objects.filter(
            user=user,
            course=course
        ).first()

        return Response({
            'eligible': eligible,
            'progress': round(progress, 1),
            'completed_lessons': completed_lessons,
            'total_lessons': total_lessons,
            'has_certificate': existing_certificate is not None,
            'certificate': CertificateSerializer(existing_certificate).data if existing_certificate else None
        })

    except Exception as e:
        print(f"❌ Certificate eligibility check error: {e}")
        return Response({
            'eligible': False,
            'reason': 'Error checking eligibility'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def search_content(request):
    """
    Search across all content for authenticated users.
    ✅ FIXED: Lessons now include enrollment_status, course_code, course_title,
              and slug so the frontend can gate access correctly.
    """
    query = request.GET.get('q', '').strip()
    if not query:
        return Response({'results': []})

    user = request.user
    results = []

    try:
        # ── Courses ──────────────────────────────────────────────────────────
        courses = Course.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(code__icontains=query),
            is_active=True
        ).distinct()

        for course in courses:
            enrollment = Enrollment.objects.filter(
                student=user,
                course=course
            ).first()

            enrollment_status = enrollment.status if enrollment else 'not_enrolled'

            results.append({
                'type':              'course',
                'id':                course.id,
                'title':             course.title,
                'description':       course.description,
                'code':              course.code,
                'category':          course.display_category,
                'level':             'beginner',
                'duration':          f"{course.duration} weeks" if course.duration else '',
                'enrollment_status': enrollment_status,
                'requires_auth':     True,
                'allow_preview':     True,
                'is_new':            course.safe_is_new,
                'is_popular':        course.safe_is_popular,
                'teacher_name':      course.teacher_name,
            })

        # ── Lessons ───────────────────────────────────────────────────────────
        lessons = Lesson.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(content__icontains=query),
            is_active=True
        ).select_related('course').distinct()

        for lesson in lessons:
            # Check whether the student is enrolled in this lesson's course
            enrollment = Enrollment.objects.filter(
                student=user,
                course=lesson.course,
                status__in=['approved', 'completed', 'enrolled']
            ).first()

            enrollment_status = enrollment.status if enrollment else 'not_enrolled'

            # Generate slug the same way the frontend does
            lesson_slug = generate_slug(lesson.title)

            results.append({
                'type':              'lesson',
                'id':                lesson.id,
                'title':             lesson.title,
                'description':       lesson.description,
                'content':           lesson.content,
                'slug':              lesson_slug,          # ✅ slug for URL building
                'duration':          f"{lesson.duration} min" if lesson.duration else '',
                'course_id':         lesson.course.id,
                'course_title':      lesson.course.title,  # ✅ shown in meta tag
                'course_code':       lesson.course.code,   # ✅ used for enrollment check
                'code':              lesson.course.code,   # keep for backwards compat
                'category':          lesson.course.display_category,
                'level':             'beginner',
                'enrollment_status': enrollment_status,    # ✅ drives Enroll vs View button
                'requires_auth':     True,
                'allow_preview':     True,
                'order':             lesson.order,
            })

        # ── Exercises (via lessons) ───────────────────────────────────────────
        exercise_lessons = Lesson.objects.filter(
            Q(exercise__icontains=query),
            is_active=True
        ).select_related('course').distinct()

        for lesson in exercise_lessons:
            if not lesson.exercise:
                continue

            try:
                exercise_data = lesson.exercise
                has_matching_question = False

                if isinstance(exercise_data, dict):
                    questions = exercise_data.get('questions', [])
                    for question in questions:
                        q_text = ' '.join([
                            str(question.get('question', '')),
                            str(question.get('text', '')),
                            str(question.get('prompt', '')),
                        ])
                        if query.lower() in q_text.lower():
                            has_matching_question = True
                            break

                if not has_matching_question:
                    continue

                enrollment = Enrollment.objects.filter(
                    student=user,
                    course=lesson.course,
                    status__in=['approved', 'completed', 'enrolled']
                ).first()

                enrollment_status = enrollment.status if enrollment else 'not_enrolled'

                results.append({
                    'type':              'exercise',
                    'id':                f"exercise_{lesson.id}",
                    'title':             f"Exercise: {lesson.title}",
                    'description':       f"Practice questions from {lesson.title}",
                    'course_title':      lesson.course.title,
                    'course_code':       lesson.course.code,
                    'code':              lesson.course.code,
                    'category':          lesson.course.display_category,
                    'level':             'beginner',
                    'enrollment_status': enrollment_status,
                    'requires_auth':     True,
                    'allow_preview':     True,
                    'lesson_id':         lesson.id,
                })
            except Exception as e:
                print(f"Error processing exercise for lesson {lesson.id}: {e}")
                continue

        return Response({'results': results})

    except Exception as e:
        print(f"Search error: {e}")
        import traceback
        traceback.print_exc()
        return Response({'results': []}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def search_public_content(request):
    """
    Search public content for guests and unauthenticated users.
    ✅ FIXED: Lessons now include slug, course_code, and course_title.
    """
    query = request.GET.get('q', '').strip()
    if not query:
        return Response({'results': []})

    results = []

    try:
        # ── Public courses ────────────────────────────────────────────────────
        courses = Course.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(code__icontains=query),
            is_active=True,
            is_public=True
        ).distinct()

        for course in courses:
            results.append({
                'type':              'course',
                'id':                course.id,
                'title':             course.title,
                'description':       course.description,
                'code':              course.code,
                'category':          course.display_category,
                'level':             'beginner',
                'duration':          f"{course.duration} weeks" if course.duration else '',
                'enrollment_status': 'not_enrolled',
                'requires_auth':     False,
                'allow_preview':     True,
                'is_new':            course.safe_is_new,
                'is_popular':        course.safe_is_popular,
                'teacher_name':      course.teacher_name,
            })

        # ── Public lessons ────────────────────────────────────────────────────
        lessons = Lesson.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query),
            is_active=True,
            course__is_public=True
        ).select_related('course').distinct()[:10]  # sensible guest limit

        for lesson in lessons:
            lesson_slug = generate_slug(lesson.title)

            results.append({
                'type':              'lesson',
                'id':                lesson.id,
                'title':             lesson.title,
                'description':       lesson.description,
                'slug':              lesson_slug,       # ✅ slug for URL building
                'duration':          f"{lesson.duration} min" if lesson.duration else '',
                'course_id':         lesson.course.id,
                'course_title':      lesson.course.title,
                'course_code':       lesson.course.code,
                'code':              lesson.course.code,
                'category':          lesson.course.display_category,
                'level':             'beginner',
                'enrollment_status': 'not_enrolled',
                'requires_auth':     False,
                'allow_preview':     True,
                'order':             lesson.order,
            })

        return Response({'results': results})

    except Exception as e:
        print(f"Public search error: {e}")
        import traceback
        traceback.print_exc()
        return Response({'results': []}, status=500)

@api_view(['GET'])
@permission_classes([AllowAny])
def search_suggestions(request):
    """
    Get search suggestions for autocomplete
    """
    query = request.GET.get('q', '').strip().lower()

    if not query or len(query) < 2:
        return Response({'suggestions': []})

    suggestions = []

    try:
        # Course title suggestions
        course_suggestions = Course.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query),
            is_active=True
        ).values('title', 'code')[:5]

        for course in course_suggestions:
            suggestions.append({
                'type': 'course',
                'title': course['title'],
                'code': course['code'],
                'display': course['title']
            })

        # Lesson title suggestions
        lesson_suggestions = Lesson.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query),
            is_active=True
        ).select_related('course').values('title', 'course__title')[:5]

        for lesson in lesson_suggestions:
            suggestions.append({
                'type': 'lesson',
                'title': lesson['title'],
                'course_title': lesson['course__title'],
                'display': f"{lesson['title']} - {lesson['course__title']}"
            })

        # Category suggestions
        categories = [cat[0] for cat in Course.CATEGORY_CHOICES]
        category_suggestions = [cat for cat in categories if query in cat.lower()]

        for category in category_suggestions[:3]:
            suggestions.append({
                'type': 'category',
                'title': category,
                'display': f"Category: {category}"
            })

        return Response({'suggestions': suggestions})

    except Exception as e:
        print(f"Search suggestions error: {e}")
        return Response({'suggestions': []})


class CommentListView(generics.ListAPIView):
    """Get comments with pagination and filtering"""
    serializer_class = CommentSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = Comment.objects.filter(is_active=True).select_related(
            'user', 'course'
        ).prefetch_related(
            'replies', 'reactions'
        ).order_by('-created_at')

        # Filter by course if provided
        course_id = self.request.query_params.get('course_id')
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

class CommentCreateView(generics.CreateAPIView):
    """Create a new comment"""
    queryset = Comment.objects.all()
    serializer_class = CommentCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        # Check if user has completed at least one lesson in the course
        course_id = request.data.get('course')
        if course_id:
            from admin_dashboard.models import Enrollment
            enrollment = Enrollment.objects.filter(
                student=request.user,
                course_id=course_id,
                status__in=['approved', 'completed']
            ).first()

            if not enrollment:
                return Response(
                    {'error': 'You must be enrolled in the course to comment.'},
                    status=status.HTTP_403_FORBIDDEN
                )

        try:
            # Use the parent create method
            response = super().create(request, *args, **kwargs)

            # Get the created comment
            comment_id = response.data.get('id')
            if comment_id:
                comment = Comment.objects.get(id=comment_id)
                # Return full comment data
                serializer = CommentSerializer(comment, context={'request': request})
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            else:
                # Fallback: get the latest comment by this user
                comment = Comment.objects.filter(user=request.user).order_by('-created_at').first()
                if comment:
                    serializer = CommentSerializer(comment, context={'request': request})
                    return Response(serializer.data, status=status.HTTP_201_CREATED)
                else:
                    return Response(
                        {'error': 'Comment created but could not retrieve data.'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

        except Exception as e:
            print(f"Error in CommentCreateView: {str(e)}")
            return Response(
                {'error': 'Failed to create comment.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ReplyCreateView(generics.CreateAPIView):
    """Create a reply to a comment"""
    queryset = Reply.objects.all()
    serializer_class = ReplyCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        # Use the parent create method to handle the creation
        response = super().create(request, *args, **kwargs)

        # Get the created reply instance
        reply_id = response.data.get('id')
        if not reply_id:
            # If no ID in response, try to get the latest reply by this user
            reply = Reply.objects.filter(
                user=request.user
            ).order_by('-created_at').first()
        else:
            reply = Reply.objects.get(id=reply_id)

        # Return the full reply data including user info
        serializer = ReplySerializer(reply, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def toggle_comment_reaction(request, comment_id):
    """Like or dislike a comment"""
    try:
        comment = Comment.objects.get(id=comment_id, is_active=True)
        reaction_type = request.data.get('reaction_type')  # 'like' or 'dislike'

        if reaction_type not in ['like', 'dislike']:
            return Response(
                {'error': 'Invalid reaction type. Use "like" or "dislike".'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user already has a reaction
        existing_reaction = CommentReaction.objects.filter(
            user=request.user,
            comment=comment
        ).first()

        if existing_reaction:
            if existing_reaction.reaction_type == reaction_type:
                # Remove reaction if clicking the same button
                existing_reaction.delete()

                # Update counts
                if reaction_type == 'like':
                    comment.likes = max(0, comment.likes - 1)
                else:
                    comment.dislikes = max(0, comment.dislikes - 1)
                comment.save()
            else:
                # Switch reaction type
                old_type = existing_reaction.reaction_type
                existing_reaction.reaction_type = reaction_type
                existing_reaction.save()

                # Update counts
                if old_type == 'like':
                    comment.likes = max(0, comment.likes - 1)
                    comment.dislikes += 1
                else:
                    comment.dislikes = max(0, comment.dislikes - 1)
                    comment.likes += 1
                comment.save()
        else:
            # Create new reaction
            CommentReaction.objects.create(
                user=request.user,
                comment=comment,
                reaction_type=reaction_type
            )

            # Update counts
            if reaction_type == 'like':
                comment.likes += 1
            else:
                comment.dislikes += 1
            comment.save()

        # Return updated comment
        serializer = CommentSerializer(comment, context={'request': request})
        return Response(serializer.data)

    except Comment.DoesNotExist:
        return Response(
            {'error': 'Comment not found.'},
            status=status.HTTP_404_NOT_FOUND
        )

@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def comment_stats(request):
    """Get comment statistics for courses"""
    course_id = request.query_params.get('course_id')

    if course_id:
        stats = Comment.objects.filter(
            course_id=course_id,
            is_active=True
        ).aggregate(
            total_comments=Count('id'),
            total_replies=Count('replies')
        )
    else:
        stats = Comment.objects.filter(is_active=True).aggregate(
            total_comments=Count('id'),
            total_replies=Count('replies')
        )

    return Response(stats)

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_comments(request):
    """Get comments by the current user"""
    comments = Comment.objects.filter(
        user=request.user,
        is_active=True
    ).select_related('course').order_by('-created_at')

    serializer = CommentSerializer(comments, many=True, context={'request': request})
    return Response(serializer.data)

class CommentDeleteView(generics.DestroyAPIView):
    """Delete a comment - only by owner"""
    queryset = Comment.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only delete their own comments
        return Comment.objects.filter(user=self.request.user)

    def perform_destroy(self, instance):
        # Soft delete instead of actual deletion
        instance.is_active = False
        instance.save()

    def destroy(self, request, *args, **kwargs):
        comment = self.get_object()
        self.perform_destroy(comment)
        return Response(
            {'detail': 'Comment deleted successfully.'},
            status=status.HTTP_200_OK
        )

class CommentUpdateView(generics.UpdateAPIView):
    """Update a comment - only by owner - FIXED VERSION"""
    queryset = Comment.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only update their own active comments
        return Comment.objects.filter(user=self.request.user, is_active=True)

    def update(self, request, *args, **kwargs):
        comment = self.get_object()

        # Only update content field
        content = request.data.get('content')
        if not content or not content.strip():
            return Response(
                {'error': 'Comment content cannot be empty.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(content) > 500:
            return Response(
                {'error': 'Comment cannot exceed 500 characters.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update the comment
        comment.content = content.strip()
        comment.edited = True  # Add this field to your model if not exists
        comment.edited_at = timezone.now()
        comment.save()

        # Return the full updated comment data
        serializer = CommentSerializer(comment, context={'request': request})
        return Response(serializer.data)

class ReplyUpdateView(generics.UpdateAPIView):
    """Update a reply - only by owner - FIXED VERSION"""
    queryset = Reply.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only update their own active replies
        return Reply.objects.filter(user=self.request.user, is_active=True)

    def update(self, request, *args, **kwargs):
        reply = self.get_object()

        # Only update content field
        content = request.data.get('content')
        if not content or not content.strip():
            return Response(
                {'error': 'Reply content cannot be empty.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(content) > 500:
            return Response(
                {'error': 'Reply cannot exceed 500 characters.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update the reply
        reply.content = content.strip()
        reply.edited = True  # Add this field to your model if not exists
        reply.edited_at = timezone.now()
        reply.save()

        # Return the full updated reply data
        serializer = ReplySerializer(reply, context={'request': request})
        return Response(serializer.data)

class ReplyDeleteView(generics.DestroyAPIView):
    """Delete a reply - only by owner"""
    queryset = Reply.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Users can only delete their own replies
        return Reply.objects.filter(user=self.request.user)

    def perform_destroy(self, instance):
        # Soft delete instead of actual deletion
        instance.is_active = False
        instance.save()

    def destroy(self, request, *args, **kwargs):
        reply = self.get_object()
        self.perform_destroy(reply)
        return Response(
            {'detail': 'Reply deleted successfully.'},
            status=status.HTTP_200_OK
        )

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def toggle_reply_reaction(request, reply_id):
    """Like or dislike a reply"""
    try:
        reply = Reply.objects.get(id=reply_id, is_active=True)
        reaction_type = request.data.get('reaction_type')  # 'like' or 'dislike'

        if reaction_type not in ['like', 'dislike']:
            return Response(
                {'error': 'Invalid reaction type. Use "like" or "dislike".'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user already has a reaction
        existing_reaction = ReplyReaction.objects.filter(
            user=request.user,
            reply=reply
        ).first()

        if existing_reaction:
            if existing_reaction.reaction_type == reaction_type:
                # Remove reaction if clicking the same button
                existing_reaction.delete()
                response_detail = f'Removed {reaction_type} from reply'
            else:
                # Switch reaction type
                existing_reaction.reaction_type = reaction_type
                existing_reaction.save()
                response_detail = f'Changed reaction to {reaction_type}'
        else:
            # Create new reaction
            ReplyReaction.objects.create(
                user=request.user,
                reply=reply,
                reaction_type=reaction_type
            )
            response_detail = f'Added {reaction_type} to reply'

        # Return updated reply with fresh data
        reply.refresh_from_db()
        serializer = ReplySerializer(reply, context={'request': request})

        return Response({
            'detail': response_detail,
            **serializer.data
        })

    except Reply.DoesNotExist:
        return Response(
            {'error': 'Reply not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        print(f"Error in toggle_reply_reaction: {e}")
        return Response(
            {'error': 'Failed to update reaction.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
class NestedReplyCreateView(generics.CreateAPIView):
    """Create a reply to a reply (nested reply)"""
    queryset = Reply.objects.all()
    serializer_class = ReplyCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        parent_reply_id = request.data.get('parent_reply')
        content = request.data.get('content')

        if not parent_reply_id:
            return Response(
                {'error': 'Parent reply ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            parent_reply = Reply.objects.get(id=parent_reply_id, is_active=True)

            # Create the nested reply
            nested_reply = Reply.objects.create(
                user=request.user,
                comment=parent_reply.comment,  # Same comment as parent
                content=content,
                parent_reply=parent_reply  # Set parent relationship
            )

            # Return the full nested reply data with proper user info
            serializer = ReplySerializer(nested_reply, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Reply.DoesNotExist:
            return Response(
                {'error': 'Parent reply not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"Error creating nested reply: {e}")
            return Response(
                {'error': 'Failed to create nested reply.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )