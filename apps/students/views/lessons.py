import logging
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.students.compat import Lesson, Enrollment, LessonProgress, Course
from apps.students.models import StudentExercise
from apps.students.serializers import (
    LessonListSerializer, LessonDetailSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_enrollment(user, lesson):
    return Enrollment.objects.filter(
        student=user, course=lesson.course, status__in=['approved', 'completed']
    ).first()


def _calculate_exercise_completion_score(lesson, user):
    """Return float 0.0–1.0 representing exercise completion."""
    try:
        student_exercise = StudentExercise.objects.filter(student=user, lesson=lesson).first()
        if not student_exercise or not student_exercise.submission_data:
            return 0.0

        if isinstance(lesson.exercise, list):
            total = len(lesson.exercise)
        elif isinstance(lesson.exercise, dict):
            if 'questions' in lesson.exercise:
                total = len(lesson.exercise['questions'])
            else:
                types = ['multiple_choice', 'fill_blank', 'paragraph', 'true_false']
                total = sum(1 for t in types if t in lesson.exercise)
        else:
            total = 0

        if total == 0:
            return 1.0

        completed = sum(
            1 for i in range(1, total + 1)
            if student_exercise.submission_data.get(f'question_{i}', {}).get('is_correct')
            or student_exercise.submission_data.get(f'question_{i}', {}).get('question_type') == 'paragraph'
        )
        return completed / total
    except Exception as e:
        logger.warning("Error calculating exercise score for lesson %s: %s", lesson.id, e)
        return 0.0


def _calculate_lesson_progress(lesson, user):
    """Return detailed progress breakdown for a lesson."""
    components = []
    details = {}
    try:
        if lesson.video_url:
            vp = LessonProgress.objects.filter(student=user, lesson=lesson).first()
            video_completed = vp.video_completed if vp else False
            video_score = 1.0 if video_completed else 0.0
            if vp and vp.engagement_data:
                eng = vp.engagement_data.get('engagement_score', 0)
                watched = vp.engagement_data.get('watched_percentage', 0)
                if video_completed:
                    video_score = 0.7 + 0.2 * (eng / 10) + 0.1 * (watched / 100)
                else:
                    video_score = min(0.5, watched / 100)
            components.append(video_score)
            details['video'] = {
                'completed': video_completed,
                'score': video_score,
                'engagement_score': vp.engagement_data.get('engagement_score', 0) if vp and vp.engagement_data else 0,
                'watched_percentage': vp.engagement_data.get('watched_percentage', 0) if vp and vp.engagement_data else 0,
            }

        if lesson.exercise:
            ex_score = _calculate_exercise_completion_score(lesson, user)
            components.append(ex_score)
            details['exercises'] = {'completed': ex_score >= 1.0, 'score': ex_score}

        if not components:
            return {'progress_percentage': 100.0, 'can_complete': True, 'component_details': details,
                    'total_components': 0, 'completed_components': 0}

        overall = sum(components) / len(components) * 100
        can_complete = all(s >= 1.0 for s in components)
        return {
            'progress_percentage': round(overall, 1),
            'can_complete': can_complete,
            'component_details': details,
            'total_components': len(components),
            'completed_components': sum(1 for s in components if s >= 1.0),
        }
    except Exception as e:
        logger.warning("Error calculating lesson progress for lesson %s: %s", lesson.id, e)
        return {'progress_percentage': 0.0, 'can_complete': False, 'component_details': {},
                'total_components': 0, 'completed_components': 0}


def _check_lesson_requirements(lesson, user):
    """Return dict describing whether lesson completion requirements are met."""
    missing = []
    met = {}
    try:
        if lesson.video_url:
            vp = LessonProgress.objects.filter(student=user, lesson=lesson).first()
            video_completed = vp and vp.video_completed
            met['video_completed'] = video_completed
            if video_completed and vp.engagement_data:
                eng = vp.engagement_data.get('engagement_score', 0)
                watched = vp.engagement_data.get('watched_percentage', 0)
                reqs = lesson.get_video_requirements() if hasattr(lesson, 'get_video_requirements') else {}
                min_eng = reqs.get('min_engagement_score', 7)
                min_watch = reqs.get('min_watch_percentage', 90)
                met['video_engagement'] = eng >= min_eng
                met['video_watched'] = watched >= min_watch
                if eng < min_eng:
                    missing.append(f'video_engagement (score: {eng}/{min_eng})')
                if watched < min_watch:
                    missing.append(f'video_coverage ({watched:.1f}% watched, need {min_watch}%)')
            elif not video_completed:
                missing.append('video_completion')
                met['video_engagement'] = False
                met['video_watched'] = False

        if lesson.exercise:
            ex_score = _calculate_exercise_completion_score(lesson, user)
            met['exercises_completed'] = ex_score >= 1.0
            if ex_score < 1.0:
                missing.append('exercises (incomplete)')
        else:
            met['exercises_completed'] = True

        return {
            'can_complete': len(missing) == 0,
            'missing': missing,
            'requirements_met': met,
            'total_requirements': len(met),
            'met_requirements': sum(1 for v in met.values() if v),
        }
    except Exception as e:
        logger.warning("Error checking lesson requirements for lesson %s: %s", lesson.id, e)
        return {'can_complete': False, 'missing': ['validation_error'], 'requirements_met': {},
                'total_requirements': 0, 'met_requirements': 0}


# ---------------------------------------------------------------------------
# Home / public lesson views
# ---------------------------------------------------------------------------

class HomeCourseLessonsView(generics.ListAPIView):
    serializer_class = LessonListSerializer
    permission_classes = []

    def get_queryset(self):
        course = get_object_or_404(Course, code=self.kwargs['course_code'], is_active=True)
        return Lesson.objects.filter(course=course, is_active=True).order_by('order')


class HomeLessonDetailView(generics.RetrieveAPIView):
    serializer_class = LessonDetailSerializer
    permission_classes = []
    queryset = Lesson.objects.filter(is_active=True)


class HomeExercisesView(generics.ListAPIView):
    serializer_class = LessonListSerializer
    permission_classes = []

    def get_queryset(self):
        return Lesson.objects.filter(is_active=True, exercise__isnull=False).order_by('order')


# ---------------------------------------------------------------------------
# Dashboard lesson views (enrolled users)
# ---------------------------------------------------------------------------

class DashboardCourseLessonsView(generics.ListAPIView):
    serializer_class = LessonListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        course = get_object_or_404(Course, code=self.kwargs['course_code'], is_active=True)
        user = self.request.user
        enrolled = Enrollment.objects.filter(
            student=user, course=course, status__in=['approved', 'completed']
        ).exists()
        if not enrolled:
            return Lesson.objects.none()
        return Lesson.objects.filter(course=course, is_active=True).order_by('order')


class StudentLessonDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, course_slug, lesson_slug):
        try:
            course = Course.objects.filter(is_active=True).filter(
                code=course_slug
            ).first() or get_object_or_404(Course, code=course_slug, is_active=True)

            lessons = Lesson.objects.filter(course=course, is_active=True)
            lesson = None
            for l in lessons:
                if self._slugify(l.title) == lesson_slug or str(l.id) == lesson_slug:
                    lesson = l
                    break

            if not lesson:
                return Response({'detail': 'Lesson not found.'}, status=status.HTTP_404_NOT_FOUND)

            serializer = LessonDetailSerializer(lesson, context={'request': request})
            return Response(serializer.data)
        except Exception as e:
            logger.exception("StudentLessonDetailAPIView error")
            return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @staticmethod
    def _slugify(text):
        import re
        return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-') if text else ''


# ---------------------------------------------------------------------------
# Lesson list / detail endpoints
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_lessons_list(request):
    user = request.user
    enrolled_course_ids = Enrollment.objects.filter(
        student=user, status__in=['approved', 'completed']
    ).values_list('course_id', flat=True)
    lessons = Lesson.objects.filter(course_id__in=enrolled_course_ids, is_active=True).order_by('course', 'order')
    serializer = LessonListSerializer(lessons, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def course_lessons_list(request, course_code):
    user = request.user
    course = get_object_or_404(Course, code=course_code, is_active=True)

    enrollment = Enrollment.objects.filter(
        student=user, course=course, status__in=['approved', 'completed']
    ).first()

    if not enrollment:
        return Response({'detail': 'Not enrolled in this course.'}, status=status.HTTP_403_FORBIDDEN)

    lessons = Lesson.objects.filter(course=course, is_active=True).order_by('order')
    serializer = LessonListSerializer(lessons, many=True, context={'request': request})
    return Response({'lessons': serializer.data, 'course_code': course_code})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_lesson_detail(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)
    if not _check_enrollment(request.user, lesson):
        return Response({'detail': 'Not enrolled in this course.'}, status=status.HTTP_403_FORBIDDEN)
    serializer = LessonDetailSerializer(lesson, context={'request': request})
    return Response(serializer.data)


# ---------------------------------------------------------------------------
# Lesson completion
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_lesson_completed(request, lesson_id):
    """Mark a lesson complete and return fresh sidebar data."""
    user = request.user
    try:
        lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)

        if not _check_enrollment(user, lesson):
            return Response({'detail': 'Not enrolled in this course.'}, status=status.HTTP_403_FORBIDDEN)

        student_exercise, _ = StudentExercise.objects.get_or_create(
            student=user, lesson=lesson,
            defaults={'completed': False, 'score': 0.0, 'submission_data': {}},
        )

        completion_check = _check_lesson_requirements(lesson, user)
        if not completion_check['can_complete']:
            return Response(
                {'detail': 'Requirements not met.', 'missing_requirements': completion_check['missing'],
                 'completion_status': completion_check},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reflection = request.data.get('reflection', '').strip()
        score = float(request.data.get('score', 0))
        total_questions = int(request.data.get('total_questions', 0))

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
                'requirements_met': completion_check['requirements_met'],
            })
            student_exercise.save()
            transaction.commit()
            student_exercise.refresh_from_db()

        all_lessons = Lesson.objects.filter(course=lesson.course, is_active=True).order_by('order')
        completed_ids = set(StudentExercise.objects.filter(
            student=user, lesson__course=lesson.course, completed=True
        ).values_list('lesson_id', flat=True))

        lessons_data = [
            {
                'id': l.id, 'title': l.title, 'description': l.description,
                'duration': l.duration, 'order': l.order,
                'completed': l.id in completed_ids,
                'created_at': l.created_at.isoformat() if l.created_at else None,
            }
            for l in all_lessons
        ]

        total = len(lessons_data)
        completed_count = len(completed_ids)
        progress = round((completed_count / total) * 100, 1) if total else 0

        return Response({
            'detail': 'Lesson completed successfully!',
            'completed': True,
            'completed_at': student_exercise.completed_at.isoformat(),
            'score': student_exercise.score,
            'total_questions': total_questions,
            'updated_lessons': lessons_data,
            'course_progress': progress,
            'total_lessons': total,
            'completed_lessons': completed_count,
            'sidebar_update': True,
            'timestamp': timezone.now().isoformat(),
        })

    except Exception as e:
        logger.exception("mark_lesson_completed error for lesson %s", lesson_id)
        return Response({'detail': f'Error completing lesson: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# Exercise submission
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_exercise_answer(request, lesson_id, exercise_id):
    """Submit an answer to a specific exercise question."""
    user = request.user
    try:
        lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)
        if not _check_enrollment(user, lesson):
            return Response({'detail': 'Not enrolled in this course.'}, status=status.HTTP_403_FORBIDDEN)

        student_exercise, _ = StudentExercise.objects.get_or_create(
            student=user, lesson=lesson,
            defaults={'completed': False, 'score': 0.0, 'submission_data': {}},
        )

        submitted_answer = request.data.get('answer')
        if submitted_answer is None:
            return Response({'detail': 'Answer is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Parse questions
        questions = []
        if lesson.exercise:
            if isinstance(lesson.exercise, list):
                questions = lesson.exercise
            elif isinstance(lesson.exercise, dict):
                if 'questions' in lesson.exercise:
                    questions = lesson.exercise['questions']
                else:
                    idx = 1
                    for ex_type in ['multiple_choice', 'fill_blank', 'paragraph', 'true_false']:
                        if ex_type in lesson.exercise:
                            ex = lesson.exercise[ex_type].copy()
                            ex['type'] = ex_type.replace('_', '-')
                            ex['id'] = ex.get('id', f'question_{idx}')
                            questions.append(ex)
                            idx += 1
            for i, q in enumerate(questions):
                if not q.get('id'):
                    q['id'] = f'question_{i + 1}'

        question = next((q for q in questions if str(q.get('id', '')) == str(exercise_id)), None)
        if not question:
            return Response({'detail': f'Question {exercise_id} not found.'}, status=status.HTTP_404_NOT_FOUND)

        q_type = question.get('type', 'multiple-choice')
        is_correct = False
        correct_answer = None

        if q_type == 'multiple-choice':
            correct_answer = question.get('correct_answer', question.get('correct', 0))
            is_correct = int(submitted_answer) == int(correct_answer)

        elif q_type in ['fill-blank', 'fill_blank']:
            correct_answer = (
                question['answers'][0] if question.get('answers')
                else question.get('answer', question.get('correct_answer', question.get('correct', '')))
            )
            if correct_answer is not None:
                def _norm(s):
                    return ' '.join(str(s).strip().lower().split())
                is_correct = _norm(correct_answer) == _norm(submitted_answer)

        elif q_type == 'paragraph':
            is_correct = True
            correct_answer = "Answer saved successfully"

        elif q_type in ['true-false', 'true_false']:
            correct_answer = question.get('correct_answer', question.get('correct', 0))
            is_correct = int(submitted_answer) == int(correct_answer)

        if not student_exercise.submission_data:
            student_exercise.submission_data = {}

        prev = student_exercise.submission_data.get(str(exercise_id), {})
        was_correct = prev.get('is_correct', False)

        student_exercise.submission_data[str(exercise_id)] = {
            'answer': submitted_answer,
            'is_correct': is_correct,
            'submitted_at': timezone.now().isoformat(),
            'question_type': q_type,
        }

        if is_correct and not was_correct:
            student_exercise.score = float(student_exercise.score or 0) + 1.0
        elif not is_correct and was_correct:
            student_exercise.score = max(0, float(student_exercise.score or 0) - 1.0)

        completed_questions = sum(
            1 for q in questions
            if student_exercise.submission_data.get(str(q.get('id', '')), {}).get('is_correct')
        )

        if questions and completed_questions >= len(questions):
            student_exercise.completed = True
            if not student_exercise.completed_at:
                student_exercise.completed_at = timezone.now()

        student_exercise.save()
        student_exercise.refresh_from_db()

        resp = {
            'detail': 'Answer submitted successfully.',
            'question_id': exercise_id,
            'submitted_answer': submitted_answer,
            'is_correct': is_correct,
            'score': float(student_exercise.score),
            'total_questions': len(questions),
            'completed_questions': completed_questions,
            'lesson_completed': student_exercise.completed,
            'completed_at': student_exercise.completed_at.isoformat() if student_exercise.completed_at else None,
        }
        if not is_correct and q_type != 'paragraph':
            resp['correct_answer'] = correct_answer
        return Response(resp)

    except Exception as e:
        logger.exception("submit_exercise_answer error for lesson %s exercise %s", lesson_id, exercise_id)
        return Response({'detail': f'Server error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_followup_answer(request, lesson_id, exercise_id):
    """Submit an answer to a follow-up question."""
    user = request.user
    lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)
    if not _check_enrollment(user, lesson):
        return Response({'detail': 'Not enrolled in this course.'}, status=status.HTTP_403_FORBIDDEN)

    student_exercise, _ = StudentExercise.objects.get_or_create(
        student=user, lesson=lesson, defaults={'completed': False, 'score': 0.0},
    )

    submitted_answer = request.data.get('answer')
    if submitted_answer is None:
        return Response({'detail': 'Answer is required.'}, status=status.HTTP_400_BAD_REQUEST)

    exercise = follow_up_data = None
    if lesson.exercise:
        try:
            exercises = (
                lesson.exercise if isinstance(lesson.exercise, list)
                else lesson.exercise.get('questions', [lesson.exercise])
                if isinstance(lesson.exercise, dict) else []
            )
            exercise = next((e for e in exercises if str(e.get('id')) == str(exercise_id)), None)
            if exercise:
                follow_up_data = exercise.get('follow_up')
                if not follow_up_data and exercise.get('type') == 'multiple-choice':
                    opt = exercise.get('options', [])[exercise.get('correct', 0)]
                    follow_up_data = {
                        'question': f'Complete: The correct answer to "{exercise.get("question","")[:50]}..." is ___.',
                        'correct_answer': opt,
                        'explanation': f'The correct answer is "{opt}".',
                    }
        except Exception:
            pass

    if not exercise or not follow_up_data:
        return Response({'detail': 'Follow-up question not found.'}, status=status.HTTP_404_NOT_FOUND)

    correct_answer = follow_up_data.get('correct_answer', '')
    is_correct = str(submitted_answer).strip().lower() == str(correct_answer).strip().lower()
    if is_correct:
        student_exercise.score += 0.5

    if not student_exercise.additional_data:
        student_exercise.additional_data = {}
    student_exercise.additional_data[f'followup_{exercise_id}'] = {
        'answer': submitted_answer, 'correct': is_correct, 'timestamp': timezone.now().isoformat(),
    }
    student_exercise.save()

    return Response({
        'detail': 'Follow-up submitted.',
        'exercise_id': exercise_id,
        'submitted_answer': submitted_answer,
        'correct_answer': correct_answer,
        'is_correct': is_correct,
        'explanation': follow_up_data.get('explanation', ''),
        'score': student_exercise.score,
        'completed': student_exercise.completed,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_exercise_progress(request, lesson_id):
    user = request.user
    lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)
    if not _check_enrollment(user, lesson):
        return Response({'detail': 'Not enrolled.'}, status=status.HTTP_403_FORBIDDEN)

    se = StudentExercise.objects.filter(student=user, lesson=lesson).first()
    data = {
        'lesson_id': lesson_id,
        'completed': se.completed if se else False,
        'score': se.score if se else 0,
        'exercises': [],
        'follow_up_progress': {},
    }
    if se and se.additional_data:
        for key, value in se.additional_data.items():
            if key.startswith('followup_'):
                data['follow_up_progress'][key.replace('followup_', '')] = value
    return Response(data)


# ---------------------------------------------------------------------------
# Video progress
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_video_progress(request, lesson_id):
    user = request.user
    try:
        lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)
        if not _check_enrollment(user, lesson):
            return Response({'detail': 'Not enrolled.'}, status=status.HTTP_403_FORBIDDEN)

        video_progress = float(request.data.get('video_progress', 0))
        video_duration = float(request.data.get('video_duration', 0))
        watched_pct = float(request.data.get('watched_percentage', 0))
        engagement = int(request.data.get('engagement_score', 0))

        video_finished = video_progress >= video_duration * 0.98 if video_duration > 0 else False
        should_complete = video_finished and watched_pct >= 85 and engagement >= 7

        progress, created = LessonProgress.objects.get_or_create(
            student=user, lesson=lesson,
            defaults={
                'video_progress': video_progress,
                'video_duration': video_duration,
                'video_completed': should_complete,
                'engagement_data': {'engagement_score': engagement, 'watched_percentage': watched_pct},
            },
        )

        if not created:
            progress.video_progress = max(progress.video_progress, video_progress)
            if video_duration > 0:
                progress.video_duration = video_duration
            if not progress.engagement_data:
                progress.engagement_data = {}
            progress.engagement_data.update({
                'engagement_score': max(progress.engagement_data.get('engagement_score', 0), engagement),
                'watched_percentage': max(progress.engagement_data.get('watched_percentage', 0), watched_pct),
            })
            if should_complete and not progress.video_completed:
                progress.video_completed = True
                progress.completed_at = timezone.now()
            progress.save()

        return Response({
            'detail': 'Progress updated.',
            'video_progress': progress.video_progress,
            'video_completed': progress.video_completed,
            'watched_percentage': progress.engagement_data.get('watched_percentage', 0),
            'engagement_score': progress.engagement_data.get('engagement_score', 0),
        })

    except Exception as e:
        logger.exception("update_video_progress error for lesson %s", lesson_id)
        return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_video_progress(request, lesson_id):
    user = request.user
    try:
        lesson = get_object_or_404(Lesson, id=lesson_id, is_active=True)
        if not _check_enrollment(user, lesson):
            return Response({'detail': 'Not enrolled.'}, status=status.HTTP_403_FORBIDDEN)

        vp = LessonProgress.objects.filter(student=user, lesson=lesson).first()
        se = StudentExercise.objects.filter(student=user, lesson=lesson).first()
        lesson_progress = _calculate_lesson_progress(lesson, user)

        return Response({
            'video_progress': vp.video_progress if vp else 0,
            'video_duration': vp.video_duration if vp else 0,
            'video_completed': vp.video_completed if vp else False,
            'time_spent': vp.time_spent if vp else 0,
            'last_accessed': vp.last_accessed if vp else None,
            'completed_at': getattr(vp, 'completed_at', None) if vp else None,
            'engagement_data': vp.engagement_data if vp and vp.engagement_data else {
                'engagement_score': 0, 'watched_segments': [],
                'watched_percentage': 0, 'requirements_met': {}, 'tracking_sessions': [],
            },
            'lesson_completed': se.completed if se else False,
            'lesson_progress': lesson_progress,
            'completion_date': se.completed_at if se else None,
            'score': se.score if se else 0,
            'has_video': bool(lesson.video_url),
            'has_exercises': bool(lesson.exercise),
            'video_url': lesson.video_url,
            'completion_requirements': lesson.get_video_requirements() if hasattr(lesson, 'get_video_requirements') else {},
        })

    except Exception as e:
        logger.exception("get_video_progress error for lesson %s", lesson_id)
        return Response({'detail': 'Error retrieving progress.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# Exercise lists / debug
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_exercises_list(request):
    user = request.user
    try:
        exercises = StudentExercise.objects.filter(student=user).select_related(
            'lesson', 'lesson__course'
        ).order_by('-completed_at')
        data = [{
            'id': ex.id,
            'lesson_title': ex.lesson.title,
            'course_title': ex.lesson.course.title,
            'completed': ex.completed,
            'completed_at': ex.completed_at,
            'score': ex.score,
            'max_score': 1.0,
            'percentage': ex.score * 100 if ex.score else 0,
        } for ex in exercises]
        return Response(data)
    except Exception as e:
        logger.exception("student_exercises_list error")
        return Response([], status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_completed_exercises(request):
    user = request.user
    try:
        enrolled_courses = Course.objects.filter(
            enrollments__student=user,
            enrollments__status__in=['approved', 'completed'],
            is_active=True,
        ).distinct()

        all_data = []
        total_score = total_exercises = 0

        for course in enrolled_courses:
            lessons = Lesson.objects.filter(course=course, is_active=True)
            for lesson in lessons:
                total_exercises += 1
                se = StudentExercise.objects.filter(student=user, lesson=lesson).first()
                score = (se.score if se and se.score else 0)
                total_score += score
                all_data.append({
                    'lesson_id': lesson.id,
                    'lesson_title': lesson.title,
                    'course_title': course.title,
                    'course_code': course.code,
                    'completed': se.completed if se else False,
                    'score': score,
                    'completed_at': se.completed_at if se else None,
                })

        avg_grade = round((total_score / total_exercises) * 100, 1) if total_exercises else 0
        return Response({
            'exercises': all_data,
            'statistics': {
                'total_exercises': total_exercises,
                'completed_exercises': sum(1 for e in all_data if e['completed']),
                'total_score': total_score,
                'average_grade': avg_grade,
            },
        })
    except Exception as e:
        logger.exception("student_completed_exercises error")
        return Response({'detail': str(e), 'exercises': []}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_pending_exercises(request):
    user = request.user
    try:
        enrolled_courses = Course.objects.filter(
            enrollments__student=user,
            enrollments__status__in=['approved', 'completed'],
            is_active=True,
        ).distinct()

        pending = []
        for course in enrolled_courses:
            lessons = Lesson.objects.filter(course=course, is_active=True)
            for lesson in lessons:
                if not lesson.exercise:
                    continue
                se = StudentExercise.objects.filter(student=user, lesson=lesson).first()
                if not (se and se.completed):
                    pending.append({
                        'lesson_id': lesson.id,
                        'lesson_title': lesson.title,
                        'course_title': course.title,
                        'course_code': course.code,
                        'has_video': bool(lesson.video_url),
                    })
        return Response({'pending_exercises': pending, 'total_pending': len(pending)})
    except Exception as e:
        logger.exception("student_pending_exercises error")
        return Response({'detail': str(e), 'pending_exercises': []}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def debug_student_scores(request):
    user = request.user
    exercises = StudentExercise.objects.filter(student=user).select_related('lesson')
    data = [{
        'id': ex.id,
        'lesson': ex.lesson.title,
        'score': ex.score,
        'completed': ex.completed,
        'submission_count': len(ex.submission_data) if ex.submission_data else 0,
    } for ex in exercises]
    return Response({'exercises': data, 'total': len(data)})


@api_view(['GET'])
@permission_classes([])
def test_lesson(request, course_slug, lesson_slug):
    return Response({'course_slug': course_slug, 'lesson_slug': lesson_slug, 'status': 'ok'})
