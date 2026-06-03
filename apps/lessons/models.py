from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError

class Lesson(models.Model):

    VIDEO_SOURCE_CHOICES = [
        ('local', 'Local File'),
        ('youtube', 'YouTube'),
        ('vimeo', 'Vimeo'),
        ('cloud', 'Cloud Storage'),
        ('external', 'External URL'),
    ]

    VIDEO_FORMAT_CHOICES = [
        ('mp4', 'MP4'),
        ('webm', 'WebM'),
        ('ogg', 'OGG'),
        ('youtube', 'YouTube'),
        ('vimeo', 'Vimeo'),
        ('direct', 'Direct File'),
        ('embedded', 'Embedded'),
    ]

    course = models.ForeignKey(
        'users.Course',
        on_delete=models.CASCADE,
        related_name='lessons'
    )
    title = models.CharField(max_length=255)
    order = models.PositiveIntegerField()
    description = models.TextField(blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    video_url = models.CharField(max_length=500, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    exercise = models.JSONField(blank=True, null=True)
    duration = models.PositiveIntegerField(default=30, help_text="Duration in minutes")

    video_source = models.CharField(
        max_length=20,
        choices=VIDEO_SOURCE_CHOICES,
        default='local',
        help_text="Source of the video content"
    )

    video_format = models.CharField(
        max_length=20,
        choices=VIDEO_FORMAT_CHOICES,
        default='mp4',
        help_text="Video format for proper handling"
    )

    video_codec = models.CharField(max_length=20, blank=True)
    video_bitrate = models.IntegerField(blank=True, null=True)

    video_requirements = models.JSONField(
        default=dict,
        blank=True,
        help_text="Video completion requirements"
    )

    video_duration = models.IntegerField(default=0, help_text="Duration in seconds")
    video_file_size = models.BigIntegerField(default=0, help_text="File size in bytes")
    supports_streaming = models.BooleanField(default=True)
    requires_authentication = models.BooleanField(default=True)
    allow_download = models.BooleanField(default=False)

    class Meta:
        app_label = 'lessons'
        ordering = ['order']
        unique_together = ('course', 'order')

    def __str__(self):
        return f"{self.course.title} - {self.title} (Order: {self.order})"

    # -------------------------
    # Video URL helpers
    # -------------------------
    def clean_video_url(self):
        if not self.video_url:
            return
        url = self.video_url.strip()
        if not url.startswith(('http://', 'https://', '/media/')):
            if not url.startswith('videos/'):
                url = f'videos/{url}'
            url = f'/media/{url}'
        self.video_url = url

    def detect_video_source(self):
        if not self.video_url:
            return 'local'
        url = self.video_url.lower()
        if 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        elif 'vimeo.com' in url:
            return 'vimeo'
        elif url.startswith('http') and any(ext in url for ext in ['.mp4', '.webm', '.ogg']):
            return 'external'
        elif url.startswith('/media/'):
            return 'local'
        return 'external'

    def detect_video_format(self):
        if not self.video_url:
            return 'unknown'
        url = self.video_url.lower()
        if 'localhost:8000' in url or '/media/videos/' in url:
            return 'django-backend'
        if 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        if 'vimeo.com' in url:
            return 'vimeo'
        if 'cloudinary.com' in url:
            return 'cloudinary'
        if 's3.' in url or 'amazonaws.com' in url:
            return 'aws-s3'
        if any(ext in url for ext in ['.mp4', '.webm', '.ogg']):
            return 'direct-file'
        return 'unknown'

    def get_youtube_embed_url(self):
        if not self.video_url or 'youtube' not in self.video_url:
            return self.video_url
        if 'youtube.com/embed' in self.video_url:
            return self.video_url
        video_id = None
        if 'youtube.com/watch?v=' in self.video_url:
            video_id = self.video_url.split('youtube.com/watch?v=')[1].split('&')[0]
        elif 'youtu.be/' in self.video_url:
            video_id = self.video_url.split('youtu.be/')[1].split('?')[0]
        if video_id:
            return f'https://www.youtube.com/embed/{video_id}?enablejsapi=1'
        return self.video_url

    def get_vimeo_embed_url(self):
        if not self.video_url or 'vimeo' not in self.video_url:
            return self.video_url
        video_id = None
        if 'vimeo.com/' in self.video_url:
            video_id = self.video_url.split('vimeo.com/')[1].split('/')[0]
        elif 'player.vimeo.com/video/' in self.video_url:
            video_id = self.video_url.split('player.vimeo.com/video/')[1].split('?')[0]
        if video_id:
            return f'https://player.vimeo.com/video/{video_id}'
        return self.video_url

    def get_streaming_url(self):
        if not self.video_url or not self.video_url.startswith('/media/'):
            return self.video_url
        filename = self.video_url.replace('/media/videos/', '')
        return f'http://localhost:8000/media/videos/{filename}'

    def get_video_requirements(self):
        defaults = {
            'min_watch_percentage': 90,
            'min_engagement_score': 7,
            'min_time_percentage': 50,
            'allow_skipping': False,
            'require_continuous': False,
        }
        if self.video_requirements:
            defaults.update(self.video_requirements)
        return defaults

    def get_video_config(self):
        config = {
            'url': self.video_url,
            'source': self.video_source,
            'format': self.video_format,
            'duration': self.video_duration,
            'file_size': self.video_file_size,
            'supports_streaming': self.supports_streaming,
            'requires_authentication': self.requires_authentication,
            'allow_download': self.allow_download,
        }
        if self.video_source == 'youtube':
            config['embed_url'] = self.get_youtube_embed_url()
        elif self.video_source == 'vimeo':
            config['embed_url'] = self.get_vimeo_embed_url()
        elif self.video_source == 'local':
            config['streaming_url'] = self.get_streaming_url()
        return config

    def _has_video_url_changed(self):
        if not self.pk:
            return True
        try:
            original = Lesson.objects.get(pk=self.pk)
            return original.video_url != self.video_url
        except Lesson.DoesNotExist:
            return True

    def clean(self):
        if self.order < 1:
            raise ValidationError("Order must be at least 1")
        if Lesson.objects.filter(course=self.course, order=self.order).exclude(pk=self.pk).exists():
            raise ValidationError("A lesson with this order already exists for this course")
        if self.video_url and self.video_format == 'unknown':
            self.video_format = self.detect_video_format()

    def save(self, *args, **kwargs):
        self.clean_video_url()
        if self.video_url and self._has_video_url_changed():
            self.video_source = self.detect_video_source()
            self.video_format = None
        if self.video_url and not self.video_format:
            src = self.video_source
            url = self.video_url.lower()
            if src == 'youtube':
                self.video_format = 'youtube'
            elif src == 'vimeo':
                self.video_format = 'vimeo'
            elif '.mp4' in url:
                self.video_format = 'mp4'
            elif '.webm' in url:
                self.video_format = 'webm'
            elif '.ogg' in url:
                self.video_format = 'ogg'
            else:
                self.video_format = 'direct'
        super().save(*args, **kwargs)


class LessonProgress(models.Model):
    student = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='lesson_progress'
    )
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='progress')

    video_progress = models.IntegerField(default=0, help_text="Video progress in seconds")
    video_duration = models.IntegerField(default=0, help_text="Total video duration in seconds")
    video_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    last_accessed = models.DateTimeField(auto_now=True)
    time_spent = models.IntegerField(default=0, help_text="Total time spent in seconds")
    session_count = models.IntegerField(default=0, help_text="Number of learning sessions")

    engagement_data = models.JSONField(default=dict, blank=True)
    watch_patterns = models.JSONField(default=list, blank=True)

    class Meta:
        app_label = 'lessons'
        unique_together = ('student', 'lesson')
        indexes = [
            models.Index(fields=['student', 'last_accessed']),
            models.Index(fields=['lesson', 'video_completed']),
        ]

    def __str__(self):
        return f"{self.student.email} - {self.lesson.title}"

    def get_engagement_score(self):
        return self.engagement_data.get('engagement_score', 0) if self.engagement_data else 0

    def get_watched_percentage(self):
        return self.engagement_data.get('watched_percentage', 0) if self.engagement_data else 0

    def get_completion_requirements_met(self):
        if not self.engagement_data:
            return False
        requirements = self.engagement_data.get('requirements_met', {})
        return all(requirements.values()) if requirements else False

    def update_engagement_data(self, **kwargs):
        if not self.engagement_data:
            self.engagement_data = {}
        self.engagement_data.update(kwargs)
        self.engagement_data['last_updated'] = timezone.now().isoformat()

    def add_watch_pattern(self, pattern_data):
        if not self.watch_patterns:
            self.watch_patterns = []
        pattern_data['timestamp'] = timezone.now().isoformat()
        self.watch_patterns.append(pattern_data)
        if len(self.watch_patterns) > 100:
            self.watch_patterns = self.watch_patterns[-100:]


class VideoAnalytics(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='video_analytics')
    date = models.DateField(default=timezone.now)

    total_views = models.IntegerField(default=0)
    unique_viewers = models.IntegerField(default=0)
    total_watch_time = models.IntegerField(default=0, help_text="Total seconds watched")
    average_engagement_score = models.FloatField(default=0.0)
    completion_rate = models.FloatField(default=0.0)

    analytics_data = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'lessons'
        unique_together = ('lesson', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"Analytics for {self.lesson.title} - {self.date}"

    @classmethod
    def update_daily_stats(cls, lesson, student=None):
        today = timezone.now().date()
        analytics, _ = cls.objects.get_or_create(
            lesson=lesson,
            date=today,
            defaults={
                'total_views': 0,
                'unique_viewers': 0,
                'total_watch_time': 0,
                'average_engagement_score': 0.0,
                'completion_rate': 0.0,
                'analytics_data': {},
            }
        )
        progress_records = LessonProgress.objects.filter(
            lesson=lesson,
            last_accessed__date=today
        )
        if progress_records.exists():
            analytics.unique_viewers = progress_records.count()
            analytics.total_watch_time = sum(p.time_spent for p in progress_records)
            scores = [p.get_engagement_score() for p in progress_records if p.get_engagement_score() > 0]
            analytics.average_engagement_score = sum(scores) / len(scores) if scores else 0
            completed = progress_records.filter(video_completed=True).count()
            analytics.completion_rate = (
                (completed / analytics.unique_viewers * 100)
                if analytics.unique_viewers > 0 else 0
            )
            analytics.save()
        return analytics