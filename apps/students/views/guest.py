import logging
import re
import uuid
from datetime import timedelta

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.students.compat import Lesson
from apps.students.compat import Course
from apps.students.models import GuestSession, GuestAccessSettings
from apps.students.serializers import GuestCourseSerializer, GuestLessonSerializer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_slug(text):
    if not text:
        return ''
    slug = text.lower()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug.strip())
    return slug


def _parse_exercises_from_lesson(exercise_data):
    """Convert DB exercise format to frontend-expected format."""
    if not exercise_data:
        return []
    exercises = []
    try:
        if isinstance(exercise_data, list):
            for i, ex in enumerate(exercise_data):
                if isinstance(ex, dict):
                    exercises.append({
                        'id': str(ex.get('id', f'question_{i + 1}')),
                        'type': ex.get('type', 'multiple-choice'),
                        'question': ex.get('question', ex.get('prompt', ex.get('text', ''))),
                        'options': ex.get('options', []),
                        'correct': ex.get('correct', ex.get('correct_answer', 0)),
                        'explanation': ex.get('explanation', ''),
                    })
        elif isinstance(exercise_data, dict):
            if 'questions' in exercise_data:
                return _parse_exercises_from_lesson(exercise_data['questions'])
            idx = 1
            for ex_type in ['multiple_choice', 'fill_blank', 'paragraph', 'true_false']:
                if ex_type in exercise_data:
                    ex = exercise_data[ex_type]
                    exercises.append({
                        'id': str(ex.get('id', f'question_{idx}')),
                        'type': ex_type.replace('_', '-'),
                        'question': ex.get('question', ex.get('text', ex.get('prompt', ''))),
                        'options': ex.get('options', []),
                        'correct': ex.get('correct_answer', ex.get('correct', 0)),
                        'explanation': ex.get('explanation', ''),
                    })
                    idx += 1
    except Exception as e:
        logger.warning("Error parsing guest exercises: %s", e)
    return exercises


def _build_guest_course_response(courses, settings):
    max_lessons = settings.max_lessons_access if settings else 3
    session_time = settings.max_session_time if settings else 600
    course_data = []
    for course in courses:
        lessons_count = course.lessons.filter(is_active=True).count()
        video_count = Lesson.objects.filter(course=course, is_active=True).exclude(
            Q(video_url__isnull=True) | Q(video_url='') | Q(video_url='null')
        ).count()
        teacher_name = None
        if course.teacher and course.teacher.user:
            teacher_name = f"{course.teacher.user.first_name} {course.teacher.user.last_name}".strip()
        course_data.append({
            'id': course.id,
            'title': course.title,
            'description': course.description,
            'code': course.code,
            'duration': getattr(course, 'duration', None),
            'price': float(course.price) if course.price else 0.0,
            'lessons_count': lessons_count,
            'total_lessons': lessons_count,
            'video_count': video_count,
            'teacher_name': teacher_name,
            'is_active': course.is_active,
            'created_at': course.created_at.isoformat() if course.created_at else None,
            'enrollment_status': 'guest_preview',
            'category': (course.get_category_display() if hasattr(course, 'get_category_display') else None) or getattr(course, 'category', 'General') or 'General',
            'is_popular': bool(getattr(course, 'is_popular', False)),
            'is_new': bool(getattr(course, 'is_new', False)),
            'is_public': bool(getattr(course, 'is_public', True)),
        })
    return {
        'courses': course_data,
        'statistics': {
            'total_courses': len(course_data),
            'max_lessons_preview': max_lessons,
            'session_duration_minutes': session_time // 60,
            'guest_mode': True,
        },
        'guest_access': {
            'enabled': settings.enabled if settings else True,
            'max_lessons': max_lessons,
            'session_time': session_time,
        },
    }


# ---------------------------------------------------------------------------
# Session endpoints
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([AllowAny])
def start_guest_session(request):
    """Start a new guest session — no auth required."""
    try:
        settings, _ = GuestAccessSettings.objects.get_or_create(
            id=1,
            defaults={'enabled': True, 'max_session_time': 600, 'max_lessons_access': 3},
        )
        if not settings.enabled:
            return Response({'detail': 'Guest access is currently disabled.'}, status=status.HTTP_403_FORBIDDEN)

        session = GuestSession.objects.create(
            session_id=uuid.uuid4(),
            expires_at=timezone.now() + timedelta(minutes=10),
            max_session_time=settings.max_session_time,
        )
        return Response({
            'session': {
                'session_id': session.session_id,
                'created_at': session.created_at,
                'expires_at': session.expires_at,
                'is_active': session.is_active,
                'time_used': session.time_used,
                'max_session_time': session.max_session_time,
                'remaining_time': session.get_remaining_time(),
                'is_expired': session.is_expired(),
            },
            'settings': {
                'max_session_time': settings.max_session_time,
                'max_lessons_access': settings.max_lessons_access,
            },
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.exception("start_guest_session error")
        return Response({'detail': 'Failed to start guest session.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def validate_guest_session(request, session_id):
    if request.user.is_authenticated:
        return Response(
            {'detail': 'User is authenticated. Guest session not needed.', 'user_authenticated': True},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        session = GuestSession.objects.get(session_id=session_id, is_active=True)
    except GuestSession.DoesNotExist:
        return Response({'detail': 'Invalid or expired session.'}, status=status.HTTP_404_NOT_FOUND)

    if session.is_expired():
        session.is_active = False
        session.save()
        return Response({'detail': 'Session has expired.'}, status=status.HTTP_410_GONE)

    session.time_used += 5
    session.save()

    return Response({
        'session_id': session.session_id,
        'created_at': session.created_at,
        'expires_at': session.expires_at,
        'is_active': session.is_active,
        'time_used': session.time_used,
        'max_session_time': session.max_session_time,
        'remaining_time': session.get_remaining_time(),
        'is_expired': session.is_expired(),
        'user_authenticated': False,
    })


# ---------------------------------------------------------------------------
# Guest course endpoints
# ---------------------------------------------------------------------------

class GuestCourseListView(generics.ListAPIView):
    """All courses available for guest preview with video counts."""
    permission_classes = [AllowAny]
    pagination_class = None
    serializer_class = GuestCourseSerializer

    def get_queryset(self):
        settings = GuestAccessSettings.objects.first()
        if settings and settings.allowed_courses.exists():
            return settings.allowed_courses.filter(is_active=True).order_by('title')
        return Course.objects.filter(is_active=True).order_by('title')

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            settings = GuestAccessSettings.objects.first()
            return Response(_build_guest_course_response(queryset, settings))
        except Exception as e:
            logger.exception("GuestCourseListView error")
            return Response(_build_guest_course_response([], None))


@api_view(['GET'])
@permission_classes([AllowAny])
def guest_available_courses(request):
    """All active courses for guest access."""
    try:
        settings = GuestAccessSettings.objects.first()
        courses = Course.objects.filter(is_active=True).order_by('title')
        return Response(_build_guest_course_response(courses, settings))
    except Exception as e:
        logger.exception("guest_available_courses error")
        return Response(_build_guest_course_response([], None))


@api_view(['GET'])
@permission_classes([AllowAny])
def guest_course_detail(request, course_code):
    try:
        course = get_object_or_404(Course, code=course_code, is_active=True)
        settings = GuestAccessSettings.objects.first()
        max_lessons = settings.max_lessons_access if settings else 3

        lessons = course.lessons.filter(is_active=True).order_by('order')[:max_lessons]
        total_lessons = course.lessons.filter(is_active=True).count()
        video_count = Lesson.objects.filter(course=course, is_active=True).exclude(
            Q(video_url__isnull=True) | Q(video_url='') | Q(video_url='null')
        ).count()

        return Response({
            'id': course.id,
            'title': course.title,
            'description': course.description,
            'code': course.code,
            'duration': getattr(course, 'duration', None),
            'total_lessons': total_lessons,
            'preview_lessons': max_lessons,
            'video_count': video_count,
            'lessons': GuestLessonSerializer(lessons, many=True, context={'request': request}).data,
        })
    except Exception as e:
        logger.exception("guest_course_detail error for %s", course_code)
        return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([AllowAny])
def guest_course_lessons(request, course_code):
    try:
        course = Course.objects.get(code=course_code, is_active=True)
        settings = GuestAccessSettings.objects.first()
        max_lessons = settings.max_lessons_access if settings else 3
        lessons = course.lessons.filter(is_active=True).order_by('order')[:max_lessons]

        lesson_data = []
        for lesson in lessons:
            has_video = bool(
                lesson.video_url and isinstance(lesson.video_url, str)
                and lesson.video_url.strip() not in ('', 'null')
            )
            lesson_data.append({
                'id': lesson.id,
                'title': lesson.title,
                'description': lesson.description,
                'duration': lesson.duration,
                'order': lesson.order,
                'course_title': course.title,
                'course_code': course.code,
                'exercise_count': 1 if lesson.exercise else 0,
                'completed': False,
                'has_video': has_video,
                'video_url': lesson.video_url if has_video else None,
                'slug': _generate_slug(lesson.title),
            })
        return Response(lesson_data)
    except Course.DoesNotExist:
        return Response({'detail': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.exception("guest_course_lessons error for %s", course_code)
        return Response([], status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def get_guest_lesson_by_slug(request, course_slug, lesson_slug):
    try:
        session_id = request.GET.get('session_id')
        if not session_id:
            return Response({'error': 'Session ID required'}, status=400)

        try:
            session = GuestSession.objects.get(session_id=session_id, is_active=True)
        except GuestSession.DoesNotExist:
            return Response({'error': 'Invalid or expired session'}, status=410)

        if session.is_expired():
            session.is_active = False
            session.save()
            return Response({'error': 'Session expired'}, status=410)

        course = get_object_or_404(Course, code=course_slug, is_active=True)
        lessons = Lesson.objects.filter(course=course, is_active=True).order_by('order')

        target_lesson = None
        for lesson in lessons:
            if _generate_slug(lesson.title) == lesson_slug:
                target_lesson = lesson
                break
        if not target_lesson and lesson_slug.isdigit():
            target_lesson = Lesson.objects.filter(id=int(lesson_slug), course=course, is_active=True).first()

        if not target_lesson:
            return Response({'error': 'Lesson not found'}, status=404)

        exercises = _parse_exercises_from_lesson(target_lesson.exercise)

        return Response({
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
            'is_guest': True,
        })

    except Exception as e:
        logger.exception("get_guest_lesson_by_slug error")
        return Response({'error': f'Server error: {str(e)}'}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def guest_submit_exercise(request, lesson_id, exercise_id):
    session_id = request.data.get('session_id')
    if not session_id:
        return Response({'detail': 'Session ID required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        session = GuestSession.objects.get(session_id=session_id, is_active=True)
    except GuestSession.DoesNotExist:
        return Response({'detail': 'Invalid session.'}, status=status.HTTP_404_NOT_FOUND)

    if session.is_expired():
        return Response({'detail': 'Session expired.'}, status=status.HTTP_410_GONE)

    return Response({
        'detail': 'Exercise submitted (guest mode) — progress not saved.',
        'is_correct': True,
        'explanation': 'This is a preview. Sign up to save your progress.',
        'guest_mode': True,
    })


# ---------------------------------------------------------------------------
# CBV guest views
# ---------------------------------------------------------------------------

class GuestCourseDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = GuestCourseSerializer
    lookup_field = 'code'
    lookup_url_kwarg = 'course_code'
    queryset = Course.objects.filter(is_active=True)


class GuestCourseLessonsView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = GuestLessonSerializer

    def get_queryset(self):
        course = get_object_or_404(Course, code=self.kwargs['course_code'], is_active=True)
        settings = GuestAccessSettings.objects.first()
        max_lessons = settings.max_lessons_access if settings else 3
        return Lesson.objects.filter(course=course, is_active=True).order_by('order')[:max_lessons]


# ---------------------------------------------------------------------------
# Debug / utility endpoints
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    return Response({'status': 'ok', 'timestamp': timezone.now().isoformat()})


@api_view(['GET'])
@permission_classes([AllowAny])
def debug_courses(request):
    courses = Course.objects.filter(is_active=True).values('id', 'title', 'code', 'is_active')
    return Response({'courses': list(courses), 'total': len(courses)})


@api_view(['GET'])
@permission_classes([AllowAny])
def debug_guest_courses(request):
    settings = GuestAccessSettings.objects.first()
    courses = Course.objects.filter(is_active=True)
    return Response({
        'total_active_courses': courses.count(),
        'guest_settings': {
            'enabled': settings.enabled if settings else None,
            'max_lessons': settings.max_lessons_access if settings else None,
            'max_session_time': settings.max_session_time if settings else None,
        },
        'courses': list(courses.values('id', 'title', 'code')),
    })
