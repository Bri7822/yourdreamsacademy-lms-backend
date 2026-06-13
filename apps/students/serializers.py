from rest_framework import serializers
from django.db.models import Q
from django.utils import timezone

from apps.students.compat import Lesson, LessonProgress, Enrollment, Course, CustomUser
from .models import (
    StudentExercise, GuestSession, Certificate,
    Comment, CommentReaction, Reply,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_time_ago(date):
    now = timezone.now()
    diff = now - date
    if diff.days > 365:
        n = diff.days // 365
        return f"{n} year{'s' if n > 1 else ''} ago"
    elif diff.days > 30:
        n = diff.days // 30
        return f"{n} month{'s' if n > 1 else ''} ago"
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        n = diff.seconds // 3600
        return f"{n} hour{'s' if n > 1 else ''} ago"
    elif diff.seconds > 60:
        n = diff.seconds // 60
        return f"{n} minute{'s' if n > 1 else ''} ago"
    return "Just now"


def _safe_get(obj, attr, default=None):
    """Safely get an attribute that may not exist on the model."""
    try:
        val = getattr(obj, attr, default)
        # Handle callables like get_category_display()
        return val() if callable(val) else val
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Lesson serializer (simple)
# ---------------------------------------------------------------------------

class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ['id', 'title', 'description', 'duration', 'order', 'is_active']


# ---------------------------------------------------------------------------
# Course serializers
# ---------------------------------------------------------------------------

class CourseListSerializer(serializers.ModelSerializer):
    """
    Safe serializer — only declares fields that ALL Course models have.
    Optional fields (is_popular, is_new, duration, teacher_name, category)
    are returned via SerializerMethodFields with safe fallbacks.
    """
    progress = serializers.SerializerMethodField()
    completed_lessons = serializers.SerializerMethodField()
    total_lessons = serializers.SerializerMethodField()
    enrollment_status = serializers.SerializerMethodField()
    total_exercises = serializers.SerializerMethodField()
    video_count = serializers.SerializerMethodField()
    # Optional Course fields — safe fallbacks
    category = serializers.SerializerMethodField()
    is_popular = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            'id', 'title', 'description', 'price', 'code', 'is_active',
            'progress', 'completed_lessons', 'total_lessons', 'enrollment_status',
            'total_exercises', 'category', 'is_popular', 'is_new',
            'duration', 'teacher_name', 'video_count',
        ]

    def _user(self):
        return self.context['request'].user

    def get_progress(self, obj):
        user = self._user()
        if not user.is_authenticated:
            return 0
        total = Lesson.objects.filter(course=obj, is_active=True).count()
        if total == 0:
            return 0
        completed = StudentExercise.objects.filter(
            student=user, lesson__course=obj, completed=True
        ).count()
        return round((completed / total) * 100, 1)

    def get_completed_lessons(self, obj):
        user = self._user()
        if not user.is_authenticated:
            return 0
        return StudentExercise.objects.filter(
            student=user, lesson__course=obj, completed=True
        ).count()

    def get_total_lessons(self, obj):
        return Lesson.objects.filter(course=obj, is_active=True).count()

    def get_enrollment_status(self, obj):
        user = self._user()
        if not user.is_authenticated:
            return 'not_enrolled'
        enrollment = Enrollment.objects.filter(student=user, course=obj).first()
        return enrollment.status if enrollment else 'not_enrolled'

    def get_total_exercises(self, obj):
        try:
            return sum(
                1 for lesson in Lesson.objects.filter(course=obj, is_active=True)
                if lesson.exercise
            )
        except Exception:
            return 0

    def get_video_count(self, obj):
        try:
            return Lesson.objects.filter(course=obj, is_active=True).exclude(
                Q(video_url__isnull=True) | Q(video_url='') | Q(video_url='null')
            ).count()
        except Exception:
            return 0

    def get_category(self, obj):
        # Try get_category_display() first, then .category, then fallback
        try:
            if hasattr(obj, 'get_category_display'):
                return obj.get_category_display()
        except Exception:
            pass
        return getattr(obj, 'category', 'General') or 'General'

    def get_is_popular(self, obj):
        return bool(getattr(obj, 'is_popular', False))

    def get_is_new(self, obj):
        return bool(getattr(obj, 'is_new', False))

    def get_duration(self, obj):
        return getattr(obj, 'duration', None)

    def get_teacher_name(self, obj):
        # Try attribute first (denormalised field)
        name = getattr(obj, 'teacher_name', None)
        if name:
            return name
        # Try related teacher object
        try:
            teacher = getattr(obj, 'teacher', None)
            if teacher:
                user = getattr(teacher, 'user', None)
                if user:
                    return f"{user.first_name} {user.last_name}".strip() or user.email
        except Exception:
            pass
        return None


class CourseDetailSerializer(serializers.ModelSerializer):
    progress = serializers.SerializerMethodField()
    completed_lessons = serializers.SerializerMethodField()
    total_lessons = serializers.SerializerMethodField()
    lessons = LessonSerializer(many=True, read_only=True)
    teacher_name = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    video_count = serializers.SerializerMethodField()
    total_exercises = serializers.SerializerMethodField()
    level = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            'id', 'title', 'description', 'code', 'price', 'is_active', 'created_at',
            'progress', 'completed_lessons', 'total_lessons', 'lessons',
            'teacher_name', 'category', 'video_count', 'total_exercises', 'level',
        ]

    def _user(self):
        return self.context['request'].user

    def get_progress(self, obj):
        user = self._user()
        if not user.is_authenticated:
            return 0
        total = Lesson.objects.filter(course=obj, is_active=True).count()
        if total == 0:
            return 0
        completed = StudentExercise.objects.filter(
            student=user, lesson__course=obj, completed=True
        ).count()
        return round((completed / total) * 100, 1)

    def get_completed_lessons(self, obj):
        user = self._user()
        if not user.is_authenticated:
            return 0
        return StudentExercise.objects.filter(
            student=user, lesson__course=obj, completed=True
        ).count()

    def get_total_lessons(self, obj):
        return Lesson.objects.filter(course=obj, is_active=True).count()

    def get_teacher_name(self, obj):
        name = getattr(obj, 'teacher_name', None)
        if name:
            return name
        try:
            teacher = getattr(obj, 'teacher', None)
            if teacher:
                user = getattr(teacher, 'user', None)
                if user:
                    return f"{user.first_name} {user.last_name}".strip() or user.email
        except Exception:
            pass
        return None

    def get_category(self, obj):
        try:
            if hasattr(obj, 'get_category_display'):
                return obj.get_category_display()
        except Exception:
            pass
        return getattr(obj, 'category', 'General') or 'General'

    def get_video_count(self, obj):
        try:
            return Lesson.objects.filter(course=obj, is_active=True).exclude(
                Q(video_url__isnull=True) | Q(video_url='') | Q(video_url='null')
            ).count()
        except Exception:
            return 0

    def get_total_exercises(self, obj):
        try:
            return sum(
                1 for lesson in Lesson.objects.filter(course=obj, is_active=True)
                if lesson.exercise
            )
        except Exception:
            return 0

    def get_level(self, obj):
        val = getattr(obj, 'level', None)
        return val.capitalize() if val else 'Beginner'


# ---------------------------------------------------------------------------
# Lesson serializers
# ---------------------------------------------------------------------------

class LessonListSerializer(serializers.ModelSerializer):
    completed = serializers.SerializerMethodField()
    exercise_count = serializers.SerializerMethodField()
    has_video = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            'id', 'title', 'description', 'duration', 'order',
            'completed', 'exercise_count', 'created_at',
            'video_url', 'has_video',
        ]

    def get_completed(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        user = request.user
        if not user.is_authenticated:
            return False
        return StudentExercise.objects.filter(student=user, lesson=obj, completed=True).exists()

    def get_exercise_count(self, obj):
        ex = obj.exercise
        if ex is None:
            return 0
        # Empty dict/list counts as 0; any real content counts as 1
        if isinstance(ex, dict):
            return 1 if (ex.get('questions') or any(k in ex for k in ['multiple_choice','fill_blank','paragraph','true_false'])) else 0
        if isinstance(ex, list):
            return 1 if len(ex) > 0 else 0
        if isinstance(ex, str):
            return 1 if ex.strip() not in ('', '[]', '{}', 'null') else 0
        return 1 if ex else 0

    def get_has_video(self, obj):
        url = getattr(obj, 'video_url', None)
        return bool(url and str(url).strip() not in ('', 'null', 'undefined'))


class LessonDetailSerializer(serializers.ModelSerializer):
    exercises = serializers.SerializerMethodField()
    completed = serializers.SerializerMethodField()
    completed_at = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    teacher = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)

    class Meta:
        model = Lesson
        fields = [
            'id', 'title', 'description', 'content', 'video_url',
            'duration', 'order', 'exercises', 'completed', 'completed_at',
            'score', 'teacher', 'course_title', 'course_code', 'created_at',
        ]

    def get_exercises(self, obj):
        if not obj.exercise:
            return []
        exercises = []
        try:
            if isinstance(obj.exercise, list):
                for i, ex in enumerate(obj.exercise):
                    e = self._format_exercise(ex, i + 1)
                    if e:
                        exercises.append(e)
            elif isinstance(obj.exercise, dict):
                if 'questions' in obj.exercise:
                    for i, ex in enumerate(obj.exercise['questions']):
                        e = self._format_exercise(ex, i + 1)
                        if e:
                            exercises.append(e)
                else:
                    idx = 1
                    for ex_type in ['multiple_choice', 'fill_blank', 'paragraph', 'true_false']:
                        if ex_type in obj.exercise:
                            e = self._format_exercise_by_type(obj.exercise[ex_type], ex_type, idx)
                            if e:
                                exercises.append(e)
                                idx += 1
        except Exception:
            pass
        return exercises

    def _format_exercise(self, ex, index):
        if not isinstance(ex, dict):
            return None
        ex_type = ex.get('type', 'multiple-choice')
        if ex_type in ['fill-blank', 'fill_blank']:
            question = ex.get('text', ex.get('question', ''))
            correct = (ex['answers'][0] if ex.get('answers')
                       else ex.get('answer', ex.get('correct_answer', ex.get('correct', ''))))
        elif ex_type == 'paragraph':
            question = ex.get('prompt', ex.get('question', ''))
            correct = None
        else:
            question = ex.get('question', ex.get('prompt', ''))
            correct = ex.get('correct', ex.get('correct_answer', 0))
        return {
            'id': str(ex.get('id', f'question_{index}')),
            'type': ex_type,
            'question': question,
            'options': ex.get('options', []),
            'correct': correct,
            'explanation': ex.get('explanation', ''),
        }

    def _format_exercise_by_type(self, ex_data, ex_type, index):
        exercise = {
            'id': str(ex_data.get('id', f'question_{index}')),
            'type': ex_type.replace('_', '-'),
            'explanation': ex_data.get('explanation', ''),
        }
        if ex_type == 'multiple_choice':
            exercise.update({
                'question': ex_data.get('question', ''),
                'options': ex_data.get('options', []),
                'correct': ex_data.get('correct_answer', ex_data.get('correct', 0)),
            })
        elif ex_type == 'fill_blank':
            exercise.update({
                'question': ex_data.get('text', ex_data.get('question', '')),
                'options': [],
                'correct': (ex_data['answers'][0] if ex_data.get('answers')
                             else ex_data.get('answer', ex_data.get('correct_answer', ex_data.get('correct', '')))),
            })
        elif ex_type == 'true_false':
            exercise.update({
                'question': ex_data.get('question', ''),
                'options': ['True', 'False'],
                'correct': 0 if ex_data.get('correct_answer', True) else 1,
            })
        elif ex_type == 'paragraph':
            exercise.update({
                'question': ex_data.get('prompt', ex_data.get('question', '')),
                'options': [],
                'correct': None,
            })
        return exercise

    def get_completed(self, obj):
        user = self.context['request'].user
        return StudentExercise.objects.filter(student=user, lesson=obj, completed=True).exists()

    def get_completed_at(self, obj):
        user = self.context['request'].user
        ex = StudentExercise.objects.filter(student=user, lesson=obj, completed=True).first()
        return ex.completed_at if ex else None

    def get_score(self, obj):
        user = self.context['request'].user
        ex = StudentExercise.objects.filter(student=user, lesson=obj).first()
        return ex.score if ex else None

    def get_teacher(self, obj):
        try:
            teacher = getattr(obj.course, 'teacher', None)
            if teacher:
                user = getattr(teacher, 'user', None)
                if user:
                    return f"{user.first_name} {user.last_name}".strip()
        except Exception:
            pass
        return None


class LessonProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = LessonProgress
        fields = ['id', 'student', 'lesson', 'video_progress', 'video_completed', 'last_accessed', 'time_spent']
        read_only_fields = ['student', 'last_accessed']

    def create(self, validated_data):
        validated_data['student'] = self.context['request'].user
        return super().create(validated_data)


# ---------------------------------------------------------------------------
# Guest serializers
# ---------------------------------------------------------------------------

class GuestCourseSerializer(serializers.ModelSerializer):
    total_lessons = serializers.SerializerMethodField()
    video_count = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'code', 'duration', 'category', 'total_lessons', 'video_count']

    def get_total_lessons(self, obj):
        return obj.lessons.filter(is_active=True).count()

    def get_video_count(self, obj):
        try:
            return Lesson.objects.filter(course=obj, is_active=True).exclude(
                Q(video_url__isnull=True) | Q(video_url='') | Q(video_url='null')
            ).count()
        except Exception:
            return 0

    def get_category(self, obj):
        try:
            if hasattr(obj, 'get_category_display'):
                return obj.get_category_display()
        except Exception:
            pass
        return getattr(obj, 'category', 'General') or 'General'

    def get_duration(self, obj):
        return getattr(obj, 'duration', None)


class GuestLessonSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title')
    has_video = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = ['id', 'title', 'description', 'duration', 'order',
                  'course_title', 'video_url', 'has_video']

    def get_has_video(self, obj):
        url = getattr(obj, 'video_url', None)
        return bool(url and str(url).strip() not in ('', 'null', 'undefined'))


# ---------------------------------------------------------------------------
# Certificate serializer
# ---------------------------------------------------------------------------

class CertificateSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)
    total_lessons = serializers.SerializerMethodField()
    issue_date = serializers.SerializerMethodField()
    formatted_grade = serializers.SerializerMethodField()
    is_valid = serializers.SerializerMethodField()
    accessible = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    is_enrolled = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    teacher_name = serializers.SerializerMethodField()
    description = serializers.CharField(source='course.description', read_only=True)

    class Meta:
        model = Certificate
        fields = [
            'id', 'certificate_id', 'course_title', 'course_code', 'category',
            'teacher_name', 'total_lessons', 'description',
            'issued_date', 'issue_date', 'grade', 'formatted_grade',
            'download_url', 'is_valid', 'accessible', 'message',
            'progress', 'is_enrolled',
        ]
        read_only_fields = ['certificate_id', 'issued_date', 'download_url']

    def _user(self):
        return self.context['request'].user

    def get_issue_date(self, obj):
        return obj.issued_date.strftime('%B %d, %Y')

    def get_formatted_grade(self, obj):
        return f"{obj.grade}%"

    def get_is_valid(self, obj):
        return obj.is_valid

    def get_accessible(self, obj):
        return obj.is_valid

    def get_message(self, obj):
        return 'Certificate available for download' if obj.is_valid else 'Complete the course to access this certificate'

    def get_progress(self, obj):
        user = self._user()
        total = Lesson.objects.filter(course=obj.course, is_active=True).count()
        completed = StudentExercise.objects.filter(
            student=user, lesson__course=obj.course, completed=True
        ).count()
        return round((completed / total) * 100, 1) if total > 0 else 0

    def get_is_enrolled(self, obj):
        return Enrollment.objects.filter(
            student=self._user(), course=obj.course, status__in=['approved', 'completed']
        ).exists()

    def get_total_lessons(self, obj):
        return Lesson.objects.filter(course=obj.course, is_active=True).count()

    def get_category(self, obj):
        try:
            if hasattr(obj.course, 'get_category_display'):
                return obj.course.get_category_display()
        except Exception:
            pass
        return getattr(obj.course, 'category', 'General') or 'General'

    def get_teacher_name(self, obj):
        name = getattr(obj.course, 'teacher_name', None)
        if name:
            return name
        try:
            teacher = getattr(obj.course, 'teacher', None)
            if teacher:
                user = getattr(teacher, 'user', None)
                if user:
                    return f"{user.first_name} {user.last_name}".strip()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Comment / Reply serializers
# ---------------------------------------------------------------------------

class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ['id', 'first_name', 'last_name', 'email', 'full_name']

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()


class ReplySerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)
    user_name = serializers.SerializerMethodField()
    user_data = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()
    disliked = serializers.SerializerMethodField()
    likes = serializers.SerializerMethodField()
    dislikes = serializers.SerializerMethodField()
    nested_replies = serializers.SerializerMethodField()

    class Meta:
        model = Reply
        fields = [
            'id', 'user', 'user_name', 'user_data', 'content', 'created_at', 'date',
            'can_edit', 'can_delete', 'likes', 'dislikes', 'liked', 'disliked',
            'nested_replies', 'edited', 'edited_at',
        ]
        read_only_fields = ['user', 'created_at', 'edited', 'edited_at']

    def get_user_name(self, obj):
        try:
            name = f"{obj.user.first_name} {obj.user.last_name}".strip()
            return name or obj.user.email.split('@')[0]
        except Exception:
            return "User"

    def get_user_data(self, obj):
        try:
            return {
                'first_name': obj.user.first_name,
                'last_name': obj.user.last_name,
                'user_name': self.get_user_name(obj),
            }
        except Exception:
            return {'first_name': 'Unknown', 'last_name': 'User', 'user_name': 'Unknown User'}

    def get_date(self, obj):
        return _format_time_ago(obj.created_at)

    def _req(self):
        return self.context.get('request')

    def get_can_edit(self, obj):
        req = self._req()
        return bool(req and req.user.is_authenticated and obj.user == req.user)

    def get_can_delete(self, obj):
        req = self._req()
        return bool(req and req.user.is_authenticated and obj.user == req.user)

    def get_liked(self, obj):
        req = self._req()
        if req and req.user.is_authenticated:
            return obj.reactions.filter(user=req.user, reaction_type='like').exists()
        return False

    def get_disliked(self, obj):
        req = self._req()
        if req and req.user.is_authenticated:
            return obj.reactions.filter(user=req.user, reaction_type='dislike').exists()
        return False

    def get_likes(self, obj):
        return obj.reactions.filter(reaction_type='like').count()

    def get_dislikes(self, obj):
        return obj.reactions.filter(reaction_type='dislike').count()

    def get_nested_replies(self, obj):
        children = obj.child_replies.filter(is_active=True).order_by('created_at')
        return ReplySerializer(children, many=True, context=self.context).data


class CommentSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)
    user_name = serializers.SerializerMethodField()
    user_data = serializers.SerializerMethodField()
    course_name = serializers.CharField(source='course.title', read_only=True)
    replies = ReplySerializer(many=True, read_only=True)
    date = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()
    disliked = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = [
            'id', 'user', 'user_name', 'user_data', 'course', 'course_name', 'content',
            'created_at', 'date', 'likes', 'dislikes', 'liked', 'disliked',
            'replies', 'reply_count', 'can_edit', 'can_delete', 'edited', 'edited_at',
        ]
        read_only_fields = ['user', 'created_at', 'likes', 'dislikes', 'edited', 'edited_at']

    def get_user_name(self, obj):
        name = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return name or obj.user.email.split('@')[0]

    def get_user_data(self, obj):
        return {
            'first_name': obj.user.first_name,
            'last_name': obj.user.last_name,
            'user_name': self.get_user_name(obj),
        }

    def get_date(self, obj):
        return _format_time_ago(obj.created_at)

    def _req(self):
        return self.context.get('request')

    def get_liked(self, obj):
        req = self._req()
        if req and req.user.is_authenticated:
            return obj.reactions.filter(user=req.user, reaction_type='like').exists()
        return False

    def get_disliked(self, obj):
        req = self._req()
        if req and req.user.is_authenticated:
            return obj.reactions.filter(user=req.user, reaction_type='dislike').exists()
        return False

    def get_reply_count(self, obj):
        return obj.replies.count()

    def get_can_edit(self, obj):
        req = self._req()
        return bool(req and req.user.is_authenticated and obj.user == req.user)

    def get_can_delete(self, obj):
        req = self._req()
        return bool(req and req.user.is_authenticated and obj.user == req.user)


class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ['course', 'content']

    def validate(self, attrs):
        user = self.context['request'].user
        enrolled = Enrollment.objects.filter(
            student=user,
            course=attrs['course'],
            status__in=['approved', 'completed'],
        ).exists()
        if not enrolled:
            raise serializers.ValidationError("You must be enrolled in this course to comment.")
        return attrs

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError("Comment content cannot be empty.")
        if len(value) > 500:
            raise serializers.ValidationError("Comment cannot exceed 500 characters.")
        return value


class ReplyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reply
        fields = ['id', 'comment', 'content']
        read_only_fields = ['id']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError("Reply content cannot be empty.")
        if len(value) > 500:
            raise serializers.ValidationError("Reply cannot exceed 500 characters.")
        return value