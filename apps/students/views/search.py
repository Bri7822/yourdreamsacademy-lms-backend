import logging
import re

from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.students.compat import Lesson, Enrollment, Course

logger = logging.getLogger(__name__)


def _generate_slug(text):
    if not text:
        return ''
    slug = re.sub(r'[^a-z0-9\s-]', '', text.lower())
    return re.sub(r'[\s]+', '-', slug.strip())


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_content(request):
    """Full-text search for authenticated users."""
    query = request.GET.get('q', '').strip()
    if not query:
        return Response({'results': []})

    user = request.user
    results = []

    try:
        # Courses
        for course in Course.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query) | Q(code__icontains=query),
            is_active=True,
        ).distinct():
            enrollment = Enrollment.objects.filter(student=user, course=course).first()
            results.append({
                'type': 'course',
                'id': course.id,
                'title': course.title,
                'description': course.description,
                'code': course.code,
                'category': getattr(course, 'display_category', getattr(course, 'category', 'General')),
                'level': 'beginner',
                'duration': f"{getattr(course, 'duration', None)} weeks" if getattr(course, 'duration', None) else '',
                'enrollment_status': enrollment.status if enrollment else 'not_enrolled',
                'requires_auth': True,
                'allow_preview': True,
                'is_new': getattr(course, 'safe_is_new', False),
                'is_popular': getattr(course, 'safe_is_popular', False),
                'teacher_name': getattr(course, 'teacher_name', None),
            })

        # Lessons
        for lesson in Lesson.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query) | Q(content__icontains=query),
            is_active=True,
        ).select_related('course').distinct():
            enrollment = Enrollment.objects.filter(
                student=user, course=lesson.course, status__in=['approved', 'completed', 'enrolled']
            ).first()
            results.append({
                'type': 'lesson',
                'id': lesson.id,
                'title': lesson.title,
                'description': lesson.description,
                'content': lesson.content,
                'slug': _generate_slug(lesson.title),
                'duration': f"{lesson.duration} min" if lesson.duration else '',
                'course_id': lesson.course.id,
                'course_title': lesson.course.title,
                'course_code': lesson.course.code,
                'code': lesson.course.code,
                'category': getattr(lesson.course, 'display_category', getattr(lesson.course, 'category', 'General')),
                'level': 'beginner',
                'enrollment_status': enrollment.status if enrollment else 'not_enrolled',
                'requires_auth': True,
                'allow_preview': True,
                'order': lesson.order,
            })

        # Exercises
        for lesson in Lesson.objects.filter(
            Q(exercise__icontains=query), is_active=True
        ).select_related('course').distinct():
            if not lesson.exercise:
                continue
            try:
                questions = lesson.exercise.get('questions', []) if isinstance(lesson.exercise, dict) else []
                matching = any(
                    query.lower() in ' '.join([
                        str(q.get('question', '')), str(q.get('text', '')), str(q.get('prompt', ''))
                    ]).lower()
                    for q in questions
                )
                if not matching:
                    continue
                enrollment = Enrollment.objects.filter(
                    student=user, course=lesson.course, status__in=['approved', 'completed', 'enrolled']
                ).first()
                results.append({
                    'type': 'exercise',
                    'id': f"exercise_{lesson.id}",
                    'title': f"Exercise: {lesson.title}",
                    'description': f"Practice questions from {lesson.title}",
                    'course_title': lesson.course.title,
                    'course_code': lesson.course.code,
                    'code': lesson.course.code,
                    'category': getattr(lesson.course, 'display_category', getattr(lesson.course, 'category', 'General')),
                    'level': 'beginner',
                    'enrollment_status': enrollment.status if enrollment else 'not_enrolled',
                    'requires_auth': True,
                    'allow_preview': True,
                    'lesson_id': lesson.id,
                })
            except Exception as e:
                logger.warning("Error processing exercise search for lesson %s: %s", lesson.id, e)

        return Response({'results': results})

    except Exception as e:
        logger.exception("search_content error")
        return Response({'results': []}, status=500)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def search_public_content(request):
    """Search public content for guests."""
    query = request.GET.get('q', '').strip()
    if not query:
        return Response({'results': []})
    results = []
    try:
        for course in Course.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query) | Q(code__icontains=query),
            is_active=True,
        ).distinct():
            results.append({
                'type': 'course', 'id': course.id, 'title': course.title,
                'description': course.description, 'code': course.code,
                'category': getattr(course, 'display_category', getattr(course, 'category', 'General')),
                'level': 'beginner',
                'duration': f"{getattr(course, 'duration', None)} weeks" if getattr(course, 'duration', None) else '',
                'enrollment_status': 'not_enrolled', 'requires_auth': False, 'allow_preview': True,
                'is_new': getattr(course, 'safe_is_new', False),
                'is_popular': getattr(course, 'safe_is_popular', False),
                'teacher_name': getattr(course, 'teacher_name', None),
            })

        for lesson in Lesson.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query),
            is_active=True, course__is_active=True,
        ).select_related('course').distinct()[:10]:
            results.append({
                'type': 'lesson', 'id': lesson.id, 'title': lesson.title,
                'description': lesson.description, 'slug': _generate_slug(lesson.title),
                'duration': f"{lesson.duration} min" if lesson.duration else '',
                'course_id': lesson.course.id, 'course_title': lesson.course.title,
                'course_code': lesson.course.code, 'code': lesson.course.code,
                'category': getattr(lesson.course, 'display_category', getattr(lesson.course, 'category', 'General')),
                'level': 'beginner', 'enrollment_status': 'not_enrolled',
                'requires_auth': False, 'allow_preview': True, 'order': lesson.order,
            })

        return Response({'results': results})
    except Exception as e:
        logger.exception("search_public_content error")
        return Response({'results': []}, status=500)


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def search_suggestions(request):
    query = request.GET.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return Response({'suggestions': []})
    suggestions = []
    try:
        for course in Course.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query), is_active=True
        ).values('title', 'code')[:5]:
            suggestions.append({'type': 'course', 'title': course['title'], 'code': course['code'],
                                 'display': course['title']})

        for lesson in Lesson.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query), is_active=True
        ).select_related('course').values('title', 'course__title')[:5]:
            suggestions.append({'type': 'lesson', 'title': lesson['title'],
                                 'course_title': lesson['course__title'],
                                 'display': f"{lesson['title']} - {lesson['course__title']}"})

        category_choices = getattr(Course, 'CATEGORY_CHOICES', [])
        for cat in [c[0] for c in category_choices if query in c[0].lower()][:3]:
            suggestions.append({'type': 'category', 'title': cat, 'display': f"Category: {cat}"})

        return Response({'suggestions': suggestions})
    except Exception as e:
        logger.exception("search_suggestions error")
        return Response({'suggestions': []})