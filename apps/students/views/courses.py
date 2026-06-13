import logging
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.students.compat import Lesson, Enrollment, Course, CustomUser, UserProfile
from apps.students.models import StudentExercise
from apps.students.serializers import CourseListSerializer, CourseDetailSerializer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_category(course):
    try:
        if hasattr(course, 'get_category_display'):
            return course.get_category_display()
    except Exception:
        pass
    return getattr(course, 'category', 'General') or 'General'


def _safe_teacher_name(course):
    name = getattr(course, 'teacher_name', None)
    if name:
        return name
    try:
        teacher = getattr(course, 'teacher', None)
        if teacher:
            user = getattr(teacher, 'user', None)
            if user:
                return f"{user.first_name} {user.last_name}".strip()
    except Exception:
        pass
    return None


def _build_course_dict(course, user=None):
    """Build a course dict that always has every key the frontend expects."""
    is_enrolled = False
    enrollment_status = 'not_enrolled'
    completed_count = 0
    progress = 0

    if user and user.is_authenticated:
        enrollment = Enrollment.objects.filter(student=user, course=course).first()
        enrollment_status = enrollment.status if enrollment else 'not_enrolled'
        is_enrolled = enrollment_status in ['approved', 'completed', 'enrolled']

        if is_enrolled:
            lessons_count = Lesson.objects.filter(course=course, is_active=True).count()
            completed_count = StudentExercise.objects.filter(
                student=user, lesson__course=course, completed=True
            ).count()
            progress = round((completed_count / lessons_count) * 100, 1) if lessons_count > 0 else 0

    lessons_count = Lesson.objects.filter(course=course, is_active=True).count()
    video_count = Lesson.objects.filter(course=course, is_active=True).exclude(
        Q(video_url__isnull=True) | Q(video_url='') | Q(video_url='null')
    ).count()
    exercises_count = sum(
        1 for lesson in Lesson.objects.filter(course=course, is_active=True)
        if lesson.exercise
    )

    return {
        'id': course.id,
        'title': course.title,
        'code': course.code,
        'description': course.description,
        'price': float(course.price) if course.price else 0.0,
        'is_active': course.is_active,
        'progress': progress,
        'completed_lessons': completed_count,
        'total_lessons': lessons_count,
        'enrollment_status': enrollment_status,
        'is_enrolled': is_enrolled,
        'total_exercises': exercises_count,
        'video_count': video_count,
        'category': _safe_category(course),
        'is_popular': bool(getattr(course, 'is_popular', False)),
        'is_new': bool(getattr(course, 'is_new', False)),
        'duration': getattr(course, 'duration', None),
        'teacher_name': _safe_teacher_name(course),
        'created_at': course.created_at.isoformat() if getattr(course, 'created_at', None) else None,
    }


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class StudentCourseListView(generics.GenericAPIView):
    """Authenticated: all courses with enrollment status. Enrolled sorted first."""
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None  # disable global pagination

    def get(self, request, *args, **kwargs):
        user = request.user
        courses = Course.objects.filter(is_active=True).order_by('title')
        all_courses_data = [_build_course_dict(c, user) for c in courses]

        # Enrolled courses first
        all_courses_data.sort(key=lambda x: (not x['is_enrolled'], x['title']))

        enrolled_count = sum(1 for c in all_courses_data if c['is_enrolled'])
        completed_courses = sum(1 for c in all_courses_data if c['progress'] == 100)

        return Response({
            'courses': all_courses_data,
            'statistics': {
                'total_courses': len(all_courses_data),
                'enrolled_courses': enrolled_count,
                'completed_courses': completed_courses,
                'active_courses': enrolled_count - completed_courses,
            },
        })


class HomeCourseListView(generics.GenericAPIView):
    """Public: all active courses — no auth required."""
    permission_classes = []
    authentication_classes = [JWTAuthentication]  # optional: token=user, no token=anon
    pagination_class = None

    def get(self, request, *args, **kwargs):
        courses = Course.objects.filter(is_active=True).order_by('title')
        user = request.user if request.user.is_authenticated else None
        courses_data = [_build_course_dict(c, user) for c in courses]

        return Response({
            'courses': courses_data,
            'statistics': {
                'total_courses': len(courses_data),
            },
        })


class DashboardCourseListView(generics.GenericAPIView):
    """Authenticated: only enrolled courses."""
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get(self, request, *args, **kwargs):
        user = request.user
        enrolled_course_ids = Enrollment.objects.filter(
            student=user, status__in=['approved', 'completed', 'enrolled']
        ).values_list('course_id', flat=True)
        courses = Course.objects.filter(
            id__in=enrolled_course_ids, is_active=True
        ).order_by('title')
        courses_data = [_build_course_dict(c, user) for c in courses]

        return Response({
            'courses': courses_data,
            'total': len(courses_data),
        })


class StudentCourseDetailView(generics.RetrieveAPIView):
    serializer_class = CourseDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'code'
    lookup_url_kwarg = 'course_code'
    pagination_class = None

    def get_queryset(self):
        return Course.objects.filter(is_active=True)

    def retrieve(self, request, *args, **kwargs):
        course = self.get_object()
        serializer = self.get_serializer(course)
        user = request.user
        enrollment = Enrollment.objects.filter(student=user, course=course).first()
        total_exercises = sum(
            1 for lesson in Lesson.objects.filter(course=course, is_active=True)
            if lesson.exercise
        )
        course_data = serializer.data
        course_data['enrollment_status'] = enrollment.status if enrollment else 'not_enrolled'
        course_data['total_exercises'] = total_exercises
        return Response(course_data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def enroll_in_course(request, course_code):
    try:
        course = get_object_or_404(Course, code=course_code, is_active=True)
        user = request.user

        try:
            user_profile = user.user_profile
            user_type = user_profile.user_type
        except Exception:
            user_profile = UserProfile.objects.create(user=user, user_type='student', terms_agreed=True)
            user_type = 'student'

        if user_type in ['admin', 'teacher']:
            return Response(
                {'detail': f'You cannot enroll as a {user_type}.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        existing = Enrollment.objects.filter(student=user, course=course).first()
        if existing:
            if existing.status not in ['approved', 'completed', 'enrolled']:
                existing.status = 'approved'
                existing.save(update_fields=['status'])
                return Response({
                    'detail': f'Enrolled in "{course.title}"!',
                    'enrollment_status': existing.status,
                    'course': {'id': course.id, 'title': course.title, 'code': course.code},
                }, status=status.HTTP_200_OK)

            return Response({
                'detail': f'Already enrolled — status: {existing.status}.',
                'enrollment_status': existing.status,
                'course': {'id': course.id, 'title': course.title, 'code': course.code},
            }, status=status.HTTP_200_OK)

        enrollment = Enrollment.objects.create(student=user, course=course, status='approved')
        return Response({
            'detail': f'Successfully enrolled in "{course.title}"!',
            'enrollment_status': enrollment.status,
            'course': {'id': course.id, 'title': course.title, 'code': course.code},
        }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.exception("Enrollment error for course %s", course_code)
        return Response({'detail': f'Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_courses_with_exercises(request):
    user = request.user
    try:
        enrolled_courses = Course.objects.filter(
            enrollments__student=user,
            enrollments__status__in=['approved', 'completed'],
            is_active=True,
        ).distinct().order_by('title')

        course_data = []
        total_exercises = total_lessons = completed_courses_count = 0

        for course in enrolled_courses:
            lessons = Lesson.objects.filter(course=course, is_active=True)
            lessons_count = lessons.count()
            total_lessons += lessons_count
            exercises_count = sum(1 for l in lessons if l.exercise)
            total_exercises += exercises_count
            completed = StudentExercise.objects.filter(
                student=user, lesson__course=course, completed=True
            ).count()
            progress = round((completed / lessons_count) * 100, 1) if lessons_count else 0
            if progress == 100:
                completed_courses_count += 1

            course_data.append({
                'id': course.id,
                'title': course.title,
                'code': course.code,
                'description': course.description,
                'progress': progress,
                'total_lessons': lessons_count,
                'total_exercises': exercises_count,
                'enrollment_status': 'approved',
            })

        return Response({
            'courses': course_data,
            'total_courses': len(course_data),
            'completed_courses': completed_courses_count,
            'total_lessons': total_lessons,
            'total_exercises': total_exercises,
        })

    except Exception as e:
        logger.exception("student_courses_with_exercises error")
        return Response(
            {'detail': str(e), 'courses': [], 'total_courses': 0,
             'completed_courses': 0, 'total_lessons': 0, 'total_exercises': 0},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def student_grades_summary(request):
    user = request.user
    completed_exercises = StudentExercise.objects.filter(student=user, completed=True)
    total_score = sum(ex.score for ex in completed_exercises if ex.score)
    count = sum(1 for ex in completed_exercises if ex.score)
    average_grade = round((total_score / count) * 100) if count else 0
    return Response({'average_grade': average_grade, 'total_completed': count})