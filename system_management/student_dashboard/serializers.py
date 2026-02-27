from rest_framework import generics, permissions
from rest_framework.response import Response
from accounts.models import Course, CustomUser
from admin_dashboard.models import Lesson, Enrollment, LessonProgress
from django.db.models import Count, Q
from rest_framework.serializers import ModelSerializer
from rest_framework import serializers
from .models import(
     StudentExercise, GuestSession,
     Certificate, Comment, CommentReaction, Reply
)
from django.utils import timezone


class VideoConfigSerializer(serializers.Serializer):
    """Serializer for comprehensive video configuration"""
    url = serializers.CharField()
    source = serializers.CharField()
    format = serializers.CharField()
    mime_type = serializers.CharField(allow_null=True)
    duration = serializers.IntegerField()
    file_size = serializers.IntegerField()
    supports_streaming = serializers.BooleanField()
    requires_authentication = serializers.BooleanField()
    allow_download = serializers.BooleanField()
    embed_url = serializers.CharField(allow_null=True, required=False)
    streaming_url = serializers.CharField(allow_null=True, required=False)
    player_type = serializers.CharField(allow_null=True, required=False)
class LessonSerializer(serializers.ModelSerializer):
    """Serializer for lessons in course detail"""
    class Meta:
        model = Lesson
        fields = ['id', 'title', 'description', 'duration', 'order', 'is_active']
class CourseListSerializer(serializers.ModelSerializer):
    """Serializer for course list - NO LESSONS FIELD"""
    progress = serializers.SerializerMethodField()
    completed_lessons = serializers.SerializerMethodField()
    total_lessons = serializers.SerializerMethodField()
    enrollment_status = serializers.SerializerMethodField()
    total_exercises = serializers.SerializerMethodField()
    category = serializers.CharField(source='get_category_display', read_only=True)
    video_count = serializers.SerializerMethodField()
    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'price', 'code', 'is_active',
                 'progress', 'completed_lessons', 'total_lessons', 'enrollment_status',
                 'total_exercises', 'category', 'is_popular', 'is_new',
                 'duration', 'teacher_name', 'video_count']
        # ✅ REMOVED 'lessons' from fields

    def get_progress(self, obj):
        user = self.context['request'].user
        if not user.is_authenticated:
            return 0

        total_lessons = Lesson.objects.filter(course=obj, is_active=True).count()
        if total_lessons == 0:
            return 0

        completed_lessons = StudentExercise.objects.filter(
            student=user,
            lesson__course=obj,
            completed=True
        ).count()

        return round((completed_lessons / total_lessons) * 100, 1)

    def get_completed_lessons(self, obj):
        user = self.context['request'].user
        if not user.is_authenticated:
            return 0

        return StudentExercise.objects.filter(
            student=user,
            lesson__course=obj,
            completed=True
        ).count()

    def get_total_lessons(self, obj):
        return Lesson.objects.filter(course=obj, is_active=True).count()

    def get_enrollment_status(self, obj):
        user = self.context['request'].user
        if not user.is_authenticated:
            return 'not_enrolled'

        enrollment = Enrollment.objects.filter(student=user, course=obj).first()
        return enrollment.status if enrollment else 'not_enrolled'

    def get_total_exercises(self, obj):
        """
        ✅ FIXED: Count lessons with exercises (each lesson = 1 exercise regardless of questions)
        """
        try:
            lessons = Lesson.objects.filter(course=obj, is_active=True)
            exercises_count = 0

            for lesson in lessons:
                # Check if lesson has ANY exercise data
                if lesson.exercise:
                    # Count this lesson as having 1 exercise
                    exercises_count += 1

            (f"📊 Course {obj.code}: {exercises_count} lessons with exercises out of {lessons.count()} total lessons")
            return exercises_count

        except Exception as e:
            (f"❌ Error counting exercises for course {obj.code}: {e}")
            return 0

    def get_video_count(self, obj):
        """
        ✅ NEW: Count lessons with videos in this course
        """
        try:
            # Use cached property or calculate
            if hasattr(obj, 'video_count'):
                return obj.video_count

            lessons_with_videos = Lesson.objects.filter(
                course=obj,
                is_active=True
            ).exclude(
                Q(video_url__isnull=True) |
                Q(video_url='') |
                Q(video_url='null')
            ).count()

            return lessons_with_videos
        except Exception as e:
            (f"Error counting videos for course {obj.code}: {e}")
            return 0

class CourseDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for individual course view"""
    progress = serializers.SerializerMethodField()
    completed_lessons = serializers.SerializerMethodField()
    total_lessons = serializers.SerializerMethodField()
    lessons = LessonSerializer(many=True, read_only=True)
    teacher_name = serializers.SerializerMethodField()
    category = serializers.CharField(source='get_category_display', read_only=True)
    video_count = serializers.SerializerMethodField()
    total_exercises = serializers.SerializerMethodField()
    level = serializers.SerializerMethodField()
    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'code', 'price', 'duration',
                 'is_active', 'created_at', 'progress', 'completed_lessons',
                 'total_lessons', 'lessons', 'teacher', 'teacher_name', 'category', 'video_count', 'total_exercises', 'level']

    def get_progress(self, obj):
        user = self.context['request'].user
        if not user.is_authenticated:
            return 0

        total_lessons = Lesson.objects.filter(course=obj, is_active=True).count()
        if total_lessons == 0:
            return 0

        completed_lessons = StudentExercise.objects.filter(
            student=user,
            lesson__course=obj,
            completed=True
        ).count()

        return round((completed_lessons / total_lessons) * 100, 1)

    def get_completed_lessons(self, obj):
        user = self.context['request'].user
        if not user.is_authenticated:
            return 0

        return StudentExercise.objects.filter(
            student=user,
            lesson__course=obj,
            completed=True
        ).count()

    def get_total_lessons(self, obj):
        return Lesson.objects.filter(course=obj, is_active=True).count()

    def get_teacher_name(self, obj):
        if obj.teacher and obj.teacher.user:
            return f"{obj.teacher.user.first_name} {obj.teacher.user.last_name}".strip()
        return "No teacher assigned"

    def get_video_count(self, obj):
        """
        ✅ NEW: Count lessons with videos in this course
        """
        try:
            lessons_with_videos = Lesson.objects.filter(
                course=obj,
                is_active=True
            ).exclude(
                Q(video_url__isnull=True) |
                Q(video_url='') |
                Q(video_url='null')
            ).count()

            (f"📊 Course {obj.code}: {lessons_with_videos} lessons with videos")
            return lessons_with_videos
        except Exception as e:
            (f"Error counting videos for course {obj.code}: {e}")
            return 0

    def get_total_exercises(self, obj):
        """
        ✅ NEW: Count lessons with exercises (each lesson = 1 exercise)
        """
        try:
            lessons = Lesson.objects.filter(course=obj, is_active=True)
            exercises_count = 0

            for lesson in lessons:
                # Check if lesson has ANY exercise data
                if lesson.exercise:
                    # Count this lesson as having 1 exercise
                    exercises_count += 1

            (f"📊 CourseDetail {obj.code}: {exercises_count} lessons with exercises")
            return exercises_count

        except Exception as e:
            (f"❌ Error counting exercises for course {obj.code}: {e}")
            return 0

    def get_level(self, obj):
        """
        ✅ NEW: Get course level or return default
        """
        if hasattr(obj, 'level') and obj.level:
            return obj.level.capitalize()
        return 'Beginner'  # Default value

class ExerciseSerializer(serializers.Serializer):
    """Serializer for exercise data within lessons"""
    id = serializers.CharField()
    type = serializers.CharField()
    question = serializers.CharField()
    options = serializers.ListField(required=False)
    correct = serializers.CharField()
    explanation = serializers.CharField(required=False)
    follow_up = serializers.DictField(required=False)

class LessonDetailSerializer(serializers.ModelSerializer):
    """
    ✅ FIXED: Always returns full content regardless of completion status
    """
    exercises = serializers.SerializerMethodField()
    completed = serializers.SerializerMethodField()
    completed_at = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    teacher = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)
    video_config = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            'id', 'title', 'description', 'content', 'video_url', 'video_config',
            'duration', 'order', 'exercises', 'exercises', 'completed', 'completed_at',
            'score', 'teacher', 'course_title', 'course_code', 'created_at'
        ]

    def get_video_config(self, obj):
        """Generate comprehensive video configuration - ALWAYS included"""
        if not obj.video_url:
            return None

        original_url = obj.video_url
        url_lower = original_url.lower()

        if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            source = 'youtube'
            format_type = 'youtube'
            embed_url = self._get_youtube_embed_url(original_url)
            mime_type = None
            player_type = 'iframe'
            streaming_url = None

        elif 'vimeo.com' in url_lower:
            source = 'vimeo'
            format_type = 'vimeo'
            embed_url = self._get_vimeo_embed_url(original_url)
            mime_type = None
            player_type = 'iframe'
            streaming_url = None

        else:
            if original_url.startswith('/media/videos/'):
                normalized_url = original_url
            elif original_url.startswith('videos/'):
                normalized_url = f'/media/{original_url}'
            elif not original_url.startswith(('http://', 'https://')):
                normalized_url = f'/media/videos/{original_url}'
            else:
                normalized_url = original_url

            source = 'local' if '/media/' in normalized_url else 'external'
            format_type = obj.video_format or 'mp4'
            embed_url = None
            mime_type = f'video/{format_type}'
            player_type = 'html5'

            if source == 'local':
                streaming_url = f'http://localhost:8000{normalized_url}'
            else:
                streaming_url = normalized_url

        config = {
            'url': original_url,
            'source': source,
            'format': format_type,
            'mime_type': mime_type,
            'duration': obj.video_duration or 0,
            'file_size': obj.video_file_size or 0,
            'supports_streaming': obj.supports_streaming,
            'requires_authentication': obj.requires_authentication,
            'allow_download': obj.allow_download,
            'player_type': player_type,
        }

        if embed_url:
            config['embed_url'] = embed_url
        if streaming_url:
            config['streaming_url'] = streaming_url

        return config

    def _get_youtube_embed_url(self, url):
        url_lower = url.lower()
        if 'youtube.com/embed/' in url_lower:
            return url

        video_id = None
        if 'youtube.com/watch?v=' in url_lower:
            video_id = url.split('youtube.com/watch?v=')[1].split('&')[0]
        elif 'youtu.be/' in url_lower:
            video_id = url.split('youtu.be/')[1].split('?')[0]

        if video_id:
            return f'https://www.youtube.com/embed/{video_id}?enablejsapi=1&origin=http://localhost:5173&rel=0'
        return url

    def _get_vimeo_embed_url(self, url):
        url_lower = url.lower()
        if 'player.vimeo.com/video/' in url_lower:
            return url

        video_id = None
        if 'vimeo.com/' in url_lower:
            video_id = url.split('vimeo.com/')[1].split('/')[0].split('?')[0]

        if video_id:
            return f'https://player.vimeo.com/video/{video_id}?title=0&byline=0&portrait=0'
        return url

    def get_exercises(self, obj):
        """✅ ALWAYS parse and return exercises - regardless of completion status"""
        if not obj.exercise:
            return []

        exercises = []

        try:
            if isinstance(obj.exercise, list):
                for i, ex in enumerate(obj.exercise):
                    exercise = self._format_exercise(ex, i + 1)
                    if exercise:
                        exercises.append(exercise)
            elif isinstance(obj.exercise, dict):
                if 'questions' in obj.exercise:
                    for i, ex in enumerate(obj.exercise['questions']):
                        exercise = self._format_exercise(ex, i + 1)
                        if exercise:
                            exercises.append(exercise)
                else:
                    exercise_index = 1
                    for ex_type in ['multiple_choice', 'fill_blank', 'paragraph', 'true_false']:
                        if ex_type in obj.exercise:
                            ex_data = obj.exercise[ex_type]
                            exercise = self._format_exercise_by_type(ex_data, ex_type, exercise_index)
                            if exercise:
                                exercises.append(exercise)
                                exercise_index += 1
        except Exception as e:
            (f"Error parsing exercises: {e}")

        return exercises

    def _format_exercise_by_type(self, ex_data, ex_type, index):
        """Format exercise based on type"""
        exercise = {
            'id': str(ex_data.get('id', f'question_{index}')),
            'type': ex_type.replace('_', '-'),
            'explanation': ex_data.get('explanation', ''),
        }

        if ex_type == 'multiple_choice':
            exercise['options'] = ex_data.get('options', [])
            exercise['question'] = ex_data.get('question', '')
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
            exercise['options'] = ['True', 'False']
            exercise['question'] = ex_data.get('question', '')
            correct_val = ex_data.get('correct_answer', True)
            exercise['correct'] = 0 if correct_val else 1

        elif ex_type == 'paragraph':
            exercise['options'] = []
            exercise['question'] = ex_data.get('prompt', ex_data.get('question', ''))
            exercise['correct'] = None
            exercise['word_count'] = {
                'min': ex_data.get('word_count', {}).get('min', 1),
                'max': 3000
            }

        return exercise

    def _format_exercise(self, ex, index):
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

    def get_completed(self, obj):
        """Check if lesson is completed"""
        user = self.context['request'].user
        return StudentExercise.objects.filter(
            student=user,
            lesson=obj,
            completed=True
        ).exists()

    def get_completed_at(self, obj):
        """Get completion timestamp"""
        user = self.context['request'].user
        exercise = StudentExercise.objects.filter(
            student=user,
            lesson=obj,
            completed=True
        ).first()
        return exercise.completed_at if exercise else None

    def get_score(self, obj):
        """Get lesson score"""
        user = self.context['request'].user
        exercise = StudentExercise.objects.filter(
            student=user,
            lesson=obj
        ).first()
        return exercise.score if exercise else None

    def get_teacher(self, obj):
        """Get teacher name for the course"""
        if obj.course.teacher and obj.course.teacher.user:
            return f"{obj.course.teacher.user.first_name} {obj.course.teacher.user.last_name}".strip()
        return None
class LessonListSerializer(serializers.ModelSerializer):
    """Simplified serializer for lesson lists"""
    completed = serializers.SerializerMethodField()
    exercise_count = serializers.SerializerMethodField()
    exercise_count = serializers.SerializerMethodField()
    has_video = serializers.SerializerMethodField()
    video_config = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            'id', 'title','exercise_count', 'description', 'duration', 'order',
            'completed', 'exercise_count', 'created_at',
            'video_url',
            'has_video',
            'video_config'
        ]

    def get_completed(self, obj):
        """Check if lesson is completed by current user"""
        user = self.context['request'].user
        if not user.is_authenticated:
            return False

        return StudentExercise.objects.filter(
            student=user,
            lesson=obj,
            completed=True
        ).exists()

    def get_exercise_count(self, obj):
        """Count exercises in this lesson"""
        if not obj.exercise:
            return 0

        try:
            # if isinstance(obj.exercise, list):
            #     return len(obj.exercise)
            # elif isinstance(obj.exercise, dict):
            #     if 'questions' in obj.exercise:
            #         return len(obj.exercise.get('questions', []))
            #     else:
            #         return 1
            return 1
        except Exception:
            return 0

    def get_has_video(self, obj):
        """
        ✅ FIXED: Check if lesson has a video
        """
        if not obj.video_url:
            return False

        # Check if video_url is a valid string
        if isinstance(obj.video_url, str):
            video_url = obj.video_url.strip()
            if video_url and video_url != 'null' and video_url != 'undefined':
                return True

        return False

    def get_video_config(self, obj):
        """
        ✅ FIXED: Get comprehensive video configuration
        """
        if not obj.video_url:
            return None

        try:
            return obj.get_video_config()
        except Exception as e:
            (f"Error getting video config for lesson {obj.id}: {e}")
            return {
                'url': obj.video_url,
                'source': 'unknown',
                'format': 'unknown'
            }

class LessonProgressSerializer(serializers.ModelSerializer):
    """Serializer for lesson progress tracking"""
    class Meta:
        model = LessonProgress
        fields = [
            'id', 'student', 'lesson', 'video_progress', 'video_completed',
            'last_accessed', 'time_spent'
        ]
        read_only_fields = ['student', 'last_accessed']

    def create(self, validated_data):
        # Ensure the student is set to the current user
        validated_data['student'] = self.context['request'].user
        return super().create(validated_data)

# Guest Session Serializer
class GuestSessionSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    is_active = serializers.BooleanField()
    time_used = serializers.IntegerField()
    max_session_time = serializers.IntegerField()
    remaining_time = serializers.IntegerField()
    is_expired = serializers.BooleanField()

    # def create(self, validated_data):
    #     return GuestSession(**validated_data)

    # def update(self, instance, validated_data):
    #     for attr, value in validated_data.items():
    #         setattr(instance, attr, value)
    #     return instance

class GuestCourseSerializer(serializers.ModelSerializer):
    total_lessons = serializers.SerializerMethodField()
    video_count = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'code', 'duration', 'category', 'total_lessons', 'video_count']

    def get_total_lessons(self, obj):
        # Return the REAL total lessons count, not limited by guest access
        return obj.lessons.filter(is_active=True).count()

    def get_video_count(self, obj):
        """
        ✅ NEW: Count TOTAL videos in course for guest display
        """
        try:
            lessons_with_videos = Lesson.objects.filter(
                course=obj,
                is_active=True
            ).exclude(
                Q(video_url__isnull=True) |
                Q(video_url='') |
                Q(video_url='null')
            ).count()

            (f"📊 Guest Course {obj.code}: {lessons_with_videos} total videos")
            return lessons_with_videos
        except Exception as e:
            (f"Error counting videos for guest course {obj.code}: {e}")
            return 0
class GuestLessonSerializer(serializers.ModelSerializer):
    """
    ✅ FIXED: Guest lesson serializer with video support
    """
    course_title = serializers.CharField(source='course.title')
    has_video = serializers.SerializerMethodField()
    video_config = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = ['id', 'title', 'description', 'duration', 'order',
                 'course_title', 'video_url', 'has_video', 'video_config']

    def get_has_video(self, obj):
        return bool(obj.video_url and
                   obj.video_url.strip() and
                   obj.video_url != 'null')

    def get_video_config(self, obj):
        if not self.get_has_video(obj):
            return None
        try:
            return obj.get_video_config()
        except:
            return {'url': obj.video_url}

class CertificateSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)
    category = serializers.CharField(source='course.display_category', read_only=True)
    issue_date = serializers.SerializerMethodField()
    formatted_grade = serializers.SerializerMethodField()
    is_valid = serializers.SerializerMethodField()
    accessible = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = [
            'id', 'certificate_id', 'course_title', 'course_code',
            'issued_date', 'issue_date', 'grade', 'formatted_grade',
            'download_url', 'category', 'is_valid', 'accessible', 'message'
        ]
        read_only_fields = ['certificate_id', 'issued_date', 'download_url']

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

class CertificateSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)
    category = serializers.CharField(source='course.display_category', read_only=True)
    teacher_name = serializers.CharField(source='course.teacher_name', read_only=True)
    total_lessons = serializers.SerializerMethodField()
    description = serializers.CharField(source='course.description', read_only=True)
    issue_date = serializers.SerializerMethodField()
    formatted_grade = serializers.SerializerMethodField()
    is_valid = serializers.SerializerMethodField()
    accessible = serializers.SerializerMethodField()
    message = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    is_enrolled = serializers.SerializerMethodField()
    is_real_certificate = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = [
            'id', 'certificate_id', 'course_title', 'course_code', 'category',
            'teacher_name', 'total_lessons', 'description',
            'issued_date', 'issue_date', 'grade', 'formatted_grade',
            'download_url', 'is_valid', 'accessible', 'message',
            'progress', 'is_enrolled', 'is_real_certificate'
        ]
        read_only_fields = ['certificate_id', 'issued_date', 'download_url']

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
        # Calculate progress for this course
        user = self.context['request'].user
        total_lessons = Lesson.objects.filter(course=obj.course, is_active=True).count()
        completed_lessons = StudentExercise.objects.filter(
            student=user,
            lesson__course=obj.course,
            completed=True
        ).count()
        return round((completed_lessons / total_lessons) * 100, 1) if total_lessons > 0 else 0

    def get_is_enrolled(self, obj):
        user = self.context['request'].user
        return Enrollment.objects.filter(
            student=user,
            course=obj.course,
            status__in=['approved', 'completed']
        ).exists()

    def get_is_real_certificate(self, obj):
        return True

    def get_total_lessons(self, obj):
        return Lesson.objects.filter(course=obj.course, is_active=True).count()

class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ['id', 'first_name', 'last_name', 'email', 'full_name']

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()
class ReplySerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_data = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()
    disliked = serializers.SerializerMethodField()
    likes = serializers.SerializerMethodField()
    dislikes = serializers.SerializerMethodField()
    nested_replies = serializers.SerializerMethodField()  # Add nested replies
    show_nested_replies = serializers.SerializerMethodField()
    edited = serializers.BooleanField(read_only=True)
    edited_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Reply
        fields = [
            'id', 'user', 'user_name', 'user_data', 'content', 'created_at', 'date',
            'can_edit', 'can_delete', 'likes', 'dislikes', 'liked', 'disliked',
            'nested_replies', 'show_nested_replies', 'edited', 'edited_at'  # Include nested replies
        ]
        read_only_fields = ['user', 'created_at', 'edited', 'edited_at']

    def get_show_nested_replies(self, obj):
        """Default to False for nested replies visibility"""
        return False

    def get_user_name(self, obj):
        """Get user's full name"""
        try:
            if obj.user.first_name and obj.user.last_name:
                return f"{obj.user.first_name} {obj.user.last_name}"
            elif obj.user.first_name:
                return obj.user.first_name
            elif obj.user.last_name:
                return obj.user.last_name
            else:
                return obj.user.email.split('@')[0]  # Use email prefix as fallback
        except Exception as e:
            (f"Error getting user name for reply {obj.id}: {e}")
            return "User"

    def get_user_data(self, obj):
        """Get complete user data"""
        try:
            return {
                'first_name': obj.user.first_name,
                'last_name': obj.user.last_name,
                'user_name': self.get_user_name(obj),
                'email': obj.user.email
            }
        except Exception as e:
            (f"Error getting user data for reply {obj.id}: {e}")
            return {
                'first_name': 'Unknown',
                'last_name': 'User',
                'user_name': 'Unknown User'
            }

    def get_date(self, obj):
        return self.format_time_ago(obj.created_at)

    def get_can_edit(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.user == request.user
        return False

    def get_can_delete(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.user == request.user
        return False

    def get_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.reactions.filter(
                user=request.user,
                reaction_type='like'
            ).exists()
        return False

    def get_disliked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.reactions.filter(
                user=request.user,
                reaction_type='dislike'
            ).exists()
        return False

    def get_likes(self, obj):
        return obj.reactions.filter(reaction_type='like').count()

    def get_dislikes(self, obj):
        return obj.reactions.filter(reaction_type='dislike').count()

    def get_nested_replies(self, obj):
        """Get nested replies for this reply"""
        nested_replies = obj.nested_replies.all()
        return ReplySerializer(nested_replies, many=True, context=self.context).data

    def format_time_ago(self, date):
        now = timezone.now()
        diff = now - date

        if diff.days > 365:
            years = diff.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"

class CommentSerializer(serializers.ModelSerializer):
    user = UserProfileSerializer(read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    user_data = serializers.SerializerMethodField()
    course_name = serializers.CharField(source='course.title', read_only=True)
    replies = ReplySerializer(many=True, read_only=True)
    date = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()
    disliked = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    edited = serializers.BooleanField(read_only=True)
    edited_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Comment
        fields = [
            'id', 'user', 'user_name', 'user_data', 'course', 'course_name', 'content',
            'created_at', 'date', 'likes', 'dislikes', 'liked', 'disliked',
            'replies', 'reply_count', 'can_edit', 'can_delete', 'edited', 'edited_at'
        ]
        read_only_fields = ['user', 'created_at', 'likes', 'dislikes', 'edited', 'edited_at']

    def get_user_data(self, obj):
        return {
            'first_name': obj.user.first_name,
            'last_name': obj.user.last_name,
            'user_name': obj.user.get_full_name()
        }

    def get_date(self, obj):
        return self.format_time_ago(obj.created_at)

    def get_liked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.reactions.filter(
                user=request.user,
                reaction_type='like'
            ).exists()
        return False

    def get_disliked(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.reactions.filter(
                user=request.user,
                reaction_type='dislike'
            ).exists()
        return False

    def get_reply_count(self, obj):
        return obj.replies.count()

    def get_can_edit(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.user == request.user
        return False

    def get_can_delete(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.user == request.user
        return False

    def format_time_ago(self, date):
        now = timezone.now()
        diff = now - date

        if diff.days > 365:
            years = diff.days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        elif diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
        else:
            return "Just now"

class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comment
        fields = ['course', 'content']

    def validate(self, attrs):
        user = self.context['request'].user
        course = attrs['course']

        # Check if user is enrolled in the course
        from admin_dashboard.models import Enrollment
        enrollment = Enrollment.objects.filter(
            student=user,
            course=course,
            status__in=['approved', 'completed']
        ).first()

        if not enrollment:
            raise serializers.ValidationError("You must be enrolled in this course to comment.")

        return attrs

    def validate_content(self, value):
        if len(value.strip()) == 0:
            raise serializers.ValidationError("Comment content cannot be empty.")
        if len(value) > 500:
            raise serializers.ValidationError("Comment cannot exceed 500 characters.")
        return value

class ReplyCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reply
        fields = ['id', 'comment', 'content']
        read_only_fields = ['id']  # ID will be auto-generated

    def create(self, validated_data):
        # Ensure user is set from the request
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
    def validate_content(self, value):
        if len(value.strip()) == 0:
            raise serializers.ValidationError("Reply content cannot be empty.")
        if len(value) > 500:
            raise serializers.ValidationError("Reply cannot exceed 500 characters.")
        return value