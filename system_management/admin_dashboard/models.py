# admin models
from accounts.models import Course, CustomUser, UserProfile
from django.db import models
from django.db import transaction
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from decimal import Decimal
import json
from django.db import models
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

    course = models.ForeignKey("accounts.Course", on_delete=models.CASCADE,
        related_name="lessons" )
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

    # ENHANCED: Video format detection
    video_source = models.CharField(
        max_length=20,
        choices=VIDEO_SOURCE_CHOICES,
        default='local',
        help_text="Source of the video content"
    )

    video_format = models.CharField(
        max_length=20,
        choices=[
            ('mp4', 'MP4'),
            ('webm', 'WebM'),
            ('ogg', 'OGG'),
            ('youtube', 'YouTube'),
            ('vimeo', 'Vimeo'),
            ('direct', 'Direct File'),
            ('embedded', 'Embedded'),
        ],
        default='mp4',
        help_text="Video format for proper handling"
    )

    # Add to your Lesson model
    video_codec = models.CharField(max_length=20, blank=True)
    video_bitrate = models.IntegerField(blank=True, null=True)

    video_requirements = models.JSONField(
        default=dict,
        blank=True,
        help_text="Video completion requirements: min_watch_percentage, min_engagement_score, etc."
    )

    # Video metadata
    video_duration = models.IntegerField(default=0, help_text="Duration in seconds")
    video_file_size = models.BigIntegerField(default=0, help_text="File size in bytes")
    supports_streaming = models.BooleanField(default=True)

    # Video access control
    requires_authentication = models.BooleanField(default=True)
    allow_download = models.BooleanField(default=False)


    class Meta:
        ordering = ['order']
        unique_together = ('course', 'order')

    def __str__(self):
        return f"{self.course.title} - {self.title} (Order: {self.order})"
    def clean_video_url(self):
        """Standardize video URLs on save"""
        if not self.video_url:
            return

        url = self.video_url.strip()

        # If it's a local file without /media/ prefix, add it
        if not url.startswith(('http://', 'https://', '/media/')):
            if not url.startswith('videos/'):
                url = f'videos/{url}'
            url = f'/media/{url}'

        self.video_url = url
    def get_video_config(self):
        """Get comprehensive video configuration for frontend"""
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

        # Add source-specific configuration
        if self.video_source == 'youtube':
            config['embed_url'] = self.get_youtube_embed_url()
        elif self.video_source == 'vimeo':
            config['embed_url'] = self.get_vimeo_embed_url()
        elif self.video_source == 'local':
            config['streaming_url'] = self.get_streaming_url()

        return config

    # -----------------------------
    # Video Requirements
    # -----------------------------
    def get_video_requirements(self):
        """Get video requirements with defaults"""
        defaults = {
            'min_watch_percentage': 90,  # 90% of video must be watched
            'min_engagement_score': 7,   # Engagement score out of 10
            'min_time_percentage': 50,   # Minimum 50% of video duration in actual time
            'allow_skipping': False,     # Whether students can skip around
            'require_continuous': False  # Whether video must be watched continuously
        }

        if self.video_requirements:
            defaults.update(self.video_requirements)

        return defaults

    # -----------------------------
    # Video Format Detection
    # -----------------------------
    def detect_video_format(self):
        """Enhanced video format detection"""
        if not self.video_url:
            return 'unknown'

        url = self.video_url.lower()

        # Django backend
        if 'localhost:8000' in url or '/media/videos/' in url:
            return 'django-backend'

        # Platforms
        if 'youtube.com' in url or 'youtu.be' in url:
            return 'youtube'
        if 'vimeo.com' in url:
            return 'vimeo'

        # Cloud storage
        if 'cloudinary.com' in url:
            return 'cloudinary'
        if 's3.' in url or 'amazonaws.com' in url:
            return 'aws-s3'

        # File extensions
        if any(ext in url for ext in ['.mp4', '.webm', '.ogg']):
            return 'direct-file'

        return 'unknown'
    # -----------------------------
    # Validation
    # -----------------------------
    def clean(self):
        # Validate order
        if self.order < 1:
            raise ValidationError("Order must be at least 1")

        # Ensure unique order within course
        if Lesson.objects.filter(
            course=self.course,
            order=self.order
        ).exclude(pk=self.pk).exists():
            raise ValidationError("A lesson with this order already exists for this course")

        # Auto-detect video format
        if self.video_url and self.video_format == 'unknown':
            self.video_format = self.detect_video_format()

    # -----------------------------
    # Save
    # -----------------------------
    def save(self, *args, **kwargs):
        self.clean_video_url()  # Add this line
        if self.video_url and self.video_format == 'unknown':
            self.video_format = self.detect_video_format()
        super().save(*args, **kwargs)

    # -----------------------------
    # Video Config & Embeds
    # -----------------------------
    def get_video_player_config(self):
        """Get configuration for video player based on format"""
        config = {
            'type': self.video_format,
            'url': self.video_url,
            'requirements': self.get_video_requirements()
        }

        # Format-specific configurations
        if self.video_format == 'youtube':
            config['embed_url'] = self.get_youtube_embed_url()
        elif self.video_format == 'vimeo':
            config['embed_url'] = self.get_vimeo_embed_url()

        return config

    def get_youtube_embed_url(self):
        """Generate YouTube embed URL"""
        if not self.video_url or 'youtube' not in self.video_url:
            return self.video_url

        # If it's already an embed URL, return it
        if 'youtube.com/embed' in self.video_url:
            return self.video_url

        video_id = None
        if 'youtube.com/watch?v=' in self.video_url:
            video_id = self.video_url.split('youtube.com/watch?v=')[1].split('&')[0]
        elif 'youtu.be/' in self.video_url:
            video_id = self.video_url.split('youtu.be/')[1].split('?')[0]

        if video_id:
            return f'https://www.youtube.com/embed/{video_id}?enablejsapi=1&origin=http://localhost:5173'
        return self.video_url
    def get_vimeo_embed_url(self):
        """Generate Vimeo embed URL"""
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
        """Get streaming URL for local files"""
        if not self.video_url or not self.video_url.startswith('/media/'):
            return self.video_url

        # Convert relative media URL to absolute streaming URL
        filename = self.video_url.replace('/media/videos/', '')
        return f'http://localhost:8000/media/videos/{filename}'

    def detect_video_source(self):
        """Auto-detect video source from URL"""
        if not self.video_url:
            return 'local'

        url = self.video_url.lower()

        if 'youtube.com' in url or 'youtu.be' in url or 'youtube.com/embed' in url:
            return 'youtube'
        elif 'vimeo.com' in url:
            return 'vimeo'
        elif url.startswith('http') and any(ext in url for ext in ['.mp4', '.webm', '.ogg']):
            return 'external'
        elif url.startswith('/media/'):
            return 'local'
        else:
            return 'external'

    def _has_video_url_changed(self):
        """Check if video URL has changed"""
        if not self.pk:
            return True
        try:
            original = Lesson.objects.get(pk=self.pk)
            return original.video_url != self.video_url
        except Lesson.DoesNotExist:
            return True

    def save(self, *args, **kwargs):
        # Always detect video_source from video_url if video_url is set
        if self.video_url:
            # Check if video_url has changed
            if self._has_video_url_changed():
                self.video_source = self.detect_video_source()
                # Reset video_format to be re-determined
                self.video_format = None

            # If video_format is not set, set it based on video_source and video_url
            if not self.video_format:
                if self.video_source == 'youtube':
                    self.video_format = 'youtube'
                elif self.video_source == 'vimeo':
                    self.video_format = 'vimeo'
                elif any(ext in self.video_url.lower() for ext in ['.mp4']):
                    self.video_format = 'mp4'
                elif any(ext in self.video_url.lower() for ext in ['.webm']):
                    self.video_format = 'webm'
                elif any(ext in self.video_url.lower() for ext in ['.ogg']):
                    self.video_format = 'ogg'
                else:
                    self.video_format = 'direct'

        super().save(*args, **kwargs)

class Enrollment(models.Model):
    PENDING = 'pending'
    APPROVED = 'approved'
    COMPLETED = 'completed'
    DECLINED = 'declined'

    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (APPROVED, 'Approved'),
        (COMPLETED, 'Completed'),
        (DECLINED, 'Declined'),
    ]

    student = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE, related_name='admin_enrollments')
    course = models.ForeignKey("accounts.Course", on_delete=models.CASCADE, related_name='admin_enrollments')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('student', 'course')
        ordering = ['-enrolled_at']

    def __str__(self):
        return f"{self.student.email} - {self.course.title}"

    def clean(self):
        from django.core.exceptions import ValidationError
        # Ensure the student has a profile and is actually a student
        if not hasattr(self.student, 'user_profile'):
            raise ValidationError("Selected user has no profile")

        if self.student.user_profile.user_type != 'student':
            raise ValidationError("Selected user is not a student")

    def save(self, *args, **kwargs):
        from django.utils import timezone
        self.full_clean()
        if self.status == self.COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def progress(self):
        """Calculate progress based on completed lessons"""
        total_lessons = Lesson.objects.filter(course=self.course).count()
        if total_lessons == 0:
            return 0

        # Use string reference to avoid circular import
        from student_dashboard.models import StudentExercise
        completed_lessons = StudentExercise.objects.filter(
            student=self.student,
            lesson__course=self.course,
            completed=True
        ).count()

        return round((completed_lessons / total_lessons) * 100, 1)

    @property
    def exercises_completed(self):
        from student_dashboard.models import StudentExercise
        return StudentExercise.objects.filter(
            student=self.student,
            lesson__course=self.course,
            completed=True
        ).count()

    @property
    def exercises_total(self):
        return Lesson.objects.filter(course=self.course).count()

    @property
    def student_name(self):
        return self.student.get_full_name()

    @property
    def student_email(self):
        return self.student.email

    @property
    def course_title(self):
        return self.course.title

    @property
    def course_code(self):
        return self.course.code

class AutoApprovalSettings(models.Model):
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)

    class Meta:
        verbose_name = "Auto Approval Settings"
        verbose_name_plural = "Auto Approval Settings"

    def __str__(self):
        return f"Auto-Approval {'Enabled' if self.enabled else 'Disabled'}"

# Revenue Analytics Models
class Transaction(models.Model):
    TRANSACTION_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('refunded', 'Refunded'),
        ('failed', 'Failed'),
    ]

    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('ZAR', 'South African Rand'),
    ]

    transaction_id = models.CharField(max_length=50, unique=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='transactions')
    student = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='purchases')
    teacher = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='sales', null=True, blank=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')

    # Revenue split calculations
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2)
    teacher_payout = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS_CHOICES, default='pending')
    payment_gateway = models.CharField(max_length=50, default='PayPal')
    gateway_transaction_id = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # testing
    paypal_order_id = models.CharField(max_length=255, blank=True, null=True)
    paypal_payer_id = models.CharField(max_length=255, blank=True, null=True)
    is_sandbox = models.BooleanField(default=True)
    hosting_fee_applied = models.BooleanField(default=False)

    class Meta:
        db_table = 'revenue_transaction'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_id} - {self.course.title}"

    def save(self, *args, **kwargs):
        # Auto-generate transaction ID if not provided
        if not self.transaction_id:
            last_transaction = Transaction.objects.order_by('-id').first()
            last_id = last_transaction.id if last_transaction else 0
            self.transaction_id = f"TXN-{last_id + 1:04d}"

        # Calculate platform fee and teacher payout
        if self.teacher:  # Teacher course - 30% platform commission
            self.platform_fee = self.amount * Decimal('0.3')
            self.teacher_payout = self.amount * Decimal('0.7')
        else:  # Admin course - 100% platform commission
            self.platform_fee = self.amount
            self.teacher_payout = Decimal('0.0')

        super().save(*args, **kwargs)


class TeacherPayout(models.Model):

    PAYOUT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processed', 'Processed'),
        ('failed', 'Failed'),
    ]

    teacher = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='payouts')
    period_start = models.DateField()
    period_end = models.DateField()

    total_sales = models.DecimalField(max_digits=10, decimal_places=2)
    platform_commission = models.DecimalField(max_digits=10, decimal_places=2)
    payout_amount = models.DecimalField(max_digits=10, decimal_places=2)

    hosting_fee = models.DecimalField(max_digits=10, decimal_places=2, default=200.00)
    final_payout = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(max_length=20, choices=PAYOUT_STATUS_CHOICES, default='pending')
    processed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'revenue_teacherpayout'
        ordering = ['-period_end']

    def __str__(self):
        return f"Payout for {self.teacher.user.email} - {self.period_end}"

    def save(self, *args, **kwargs):
        # Calculate final payout
        self.final_payout = self.payout_amount - self.hosting_fee
        super().save(*args, **kwargs)


class RevenueReport(models.Model):
    REPORT_TYPE_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]

    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    period_start = models.DateField()
    period_end = models.DateField()

    total_revenue = models.DecimalField(max_digits=15, decimal_places=2)
    total_transactions = models.IntegerField()
    average_transaction_value = models.DecimalField(max_digits=10, decimal_places=2)

    platform_commission = models.DecimalField(max_digits=15, decimal_places=2)
    teacher_payouts = models.DecimalField(max_digits=15, decimal_places=2)
    hosting_fees = models.DecimalField(max_digits=15, decimal_places=2)
    net_profit = models.DecimalField(max_digits=15, decimal_places=2)

    currency_breakdown = models.JSONField(default=dict)  # { 'USD': 1000, 'ZAR': 15000 }
    top_courses = models.JSONField(default=list)  # [ {'course_id': 1, 'revenue': 500} ]

    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'revenue_report'
        ordering = ['-period_end']

    def __str__(self):
        return f"{self.report_type.capitalize()} Report - {self.period_end}"

class LessonProgress(models.Model):
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='progress')

    # Basic video tracking
    video_progress = models.IntegerField(default=0, help_text="Video progress in seconds")
    video_duration = models.IntegerField(default=0, help_text="Total video duration in seconds")
    video_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Time tracking
    last_accessed = models.DateTimeField(auto_now=True)
    time_spent = models.IntegerField(default=0, help_text="Total time spent in seconds")
    session_count = models.IntegerField(default=0, help_text="Number of learning sessions")

    # ENHANCED: Real-time engagement tracking
    engagement_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Engagement analytics: watch patterns, interaction data, etc."
    )

    # Progress analytics
    watch_patterns = models.JSONField(
        default=list,
        blank=True,
        help_text="Detailed watching patterns and segments"
    )

    class Meta:
        unique_together = ('student', 'lesson')
        indexes = [
            models.Index(fields=['student', 'last_accessed']),
            models.Index(fields=['lesson', 'video_completed']),
        ]

    def __str__(self):
        return f"{self.student.email} - {self.lesson.title}"

    def get_engagement_score(self):
        """Calculate engagement score from analytics data"""
        if not self.engagement_data:
            return 0

        return self.engagement_data.get('engagement_score', 0)

    def get_watched_percentage(self):
        """Calculate percentage of video segments watched"""
        if not self.engagement_data:
            return 0

        return self.engagement_data.get('watched_percentage', 0)

    def get_completion_requirements_met(self):
        """Check if all completion requirements are met"""
        if not self.engagement_data:
            return False

        requirements = self.engagement_data.get('requirements_met', {})
        return all(requirements.values()) if requirements else False

    def update_engagement_data(self, **kwargs):
        """Update engagement data with new metrics"""
        if not self.engagement_data:
            self.engagement_data = {}

        self.engagement_data.update(kwargs)
        self.engagement_data['last_updated'] = timezone.now().isoformat()

    def add_watch_pattern(self, pattern_data):
        """Add a watch pattern entry"""
        if not self.watch_patterns:
            self.watch_patterns = []

        pattern_data['timestamp'] = timezone.now().isoformat()
        self.watch_patterns.append(pattern_data)

        # Keep only last 100 patterns to avoid excessive data
        if len(self.watch_patterns) > 100:
            self.watch_patterns = self.watch_patterns[-100:]


# ENHANCED: Video Analytics and Reporting
class VideoAnalytics(models.Model):
    """Track detailed video analytics across all lessons"""
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='video_analytics')
    date = models.DateField(default=timezone.now)

    # Daily statistics
    total_views = models.IntegerField(default=0)
    unique_viewers = models.IntegerField(default=0)
    total_watch_time = models.IntegerField(default=0, help_text="Total seconds watched")
    average_engagement_score = models.FloatField(default=0.0)
    completion_rate = models.FloatField(default=0.0, help_text="Percentage of viewers who completed")

    # Detailed metrics
    analytics_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detailed analytics: drop-off points, replay sections, etc."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('lesson', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"Analytics for {self.lesson.title} - {self.date}"

    @classmethod
    def update_daily_stats(cls, lesson, student=None):
        """Update daily analytics for a lesson"""
        today = timezone.now().date()

        analytics, created = cls.objects.get_or_create(
            lesson=lesson,
            date=today,
            defaults={
                'total_views': 0,
                'unique_viewers': 0,
                'total_watch_time': 0,
                'average_engagement_score': 0.0,
                'completion_rate': 0.0,
                'analytics_data': {}
            }
        )

        # Recalculate stats
        progress_records = LessonProgress.objects.filter(
            lesson=lesson,
            last_accessed__date=today
        )

        if progress_records.exists():
            analytics.unique_viewers = progress_records.count()
            analytics.total_watch_time = sum(p.time_spent for p in progress_records)

            engagement_scores = [
                p.get_engagement_score() for p in progress_records
                if p.get_engagement_score() > 0
            ]
            analytics.average_engagement_score = (
                sum(engagement_scores) / len(engagement_scores)
                if engagement_scores else 0
            )

            completed_count = progress_records.filter(video_completed=True).count()
            analytics.completion_rate = (
                (completed_count / analytics.unique_viewers * 100)
                if analytics.unique_viewers > 0 else 0
            )

            analytics.save()

        return analytics
