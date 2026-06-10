from django.db import models
from django.utils import timezone
import uuid


class StudentExercise(models.Model):
    student = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='student_exercises'
    )
    lesson = models.ForeignKey(
        'lessons.Lesson',
        on_delete=models.CASCADE,
        related_name='student_exercises'
    )
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.FloatField(default=0.0)
    submission_data = models.JSONField(default=dict, blank=True)
    additional_data = models.JSONField(default=dict, blank=True)

    class Meta:
        unique_together = ('student', 'lesson')

    def __str__(self):
        return f"{self.student.email} - {self.lesson.title}"


class GuestSession(models.Model):
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    accessed_lessons = models.ManyToManyField('lessons.Lesson', blank=True)
    time_used = models.IntegerField(default=0)          # seconds
    max_session_time = models.IntegerField(default=600) # 10 minutes

    class Meta:
        db_table = 'guest_sessions'
        ordering = ['-created_at']

    def is_expired(self):
        return timezone.now() > self.expires_at or self.time_used >= self.max_session_time

    def get_remaining_time(self):
        return max(0, self.max_session_time - self.time_used)

    def get_time_remaining_display(self):
        remaining = self.get_remaining_time()
        minutes = remaining // 60
        seconds = remaining % 60
        return f"{minutes:02d}:{seconds:02d}"

    def __str__(self):
        return f"GuestSession {self.session_id}"


class GuestAccessSettings(models.Model):
    enabled = models.BooleanField(default=True)
    max_session_time = models.IntegerField(default=600)   # 10 minutes
    max_lessons_access = models.IntegerField(default=3)
    allowed_courses = models.ManyToManyField('users.Course', blank=True)

    class Meta:
        db_table = 'guest_access_settings'
        verbose_name_plural = 'Guest Access Settings'

    def __str__(self):
        return 'Guest Access Settings'


class Certificate(models.Model):
    user = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='certificates'
    )
    course = models.ForeignKey(
        'users.Course',
        on_delete=models.CASCADE,
        related_name='certificates'
    )
    lesson = models.ForeignKey(
        'lessons.Lesson',
        on_delete=models.SET_NULL,
        related_name='certificates',
        null=True,
        blank=True,
    )
    certificate_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    issued_date = models.DateTimeField(auto_now_add=True)
    grade = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    download_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'certificates_certificate'
        unique_together = ('user', 'course')

    def __str__(self):
        return f"{self.user.email} - {self.course.title}"

    def generate_certificate(self):
        return f"/api/certificates/{self.certificate_id}/download/"

    @property
    def is_valid(self):
        from apps.students.models import StudentExercise
        from apps.students.compat import Lesson, Enrollment

        enrollment = Enrollment.objects.filter(
            student=self.user,
            course=self.course,
            status='completed'
        ).first()

        if not enrollment:
            return False

        total_lessons = Lesson.objects.filter(course=self.course, is_active=True).count()
        completed_lessons = StudentExercise.objects.filter(
            student=self.user,
            lesson__course=self.course,
            completed=True
        ).count()

        return total_lessons > 0 and completed_lessons >= total_lessons


class Comment(models.Model):
    user = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='comments'
    )
    course = models.ForeignKey(
        'users.Course',
        on_delete=models.CASCADE,
        related_name='comments'
    )
    content = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes = models.PositiveIntegerField(default=0)
    dislikes = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'comments_comment'
        ordering = ['-created_at']

    def __str__(self):
        return f"Comment by {self.user.email} on {self.course.title}"


class CommentReaction(models.Model):
    REACTION_CHOICES = [
        ('like', 'Like'),
        ('dislike', 'Dislike'),
    ]

    user = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='comment_reactions'
    )
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name='reactions'
    )
    reaction_type = models.CharField(max_length=10, choices=REACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'comments_commentreaction'
        unique_together = ['user', 'comment']

    def __str__(self):
        return f"{self.user.email} {self.reaction_type}d comment {self.comment.id}"


class Reply(models.Model):
    user = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='replies'
    )
    comment = models.ForeignKey(
        Comment,
        on_delete=models.CASCADE,
        related_name='replies'
    )
    content = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    parent_reply = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='child_replies'  # renamed from nested_replies to avoid conflict with property
    )
    additional_data = models.JSONField(default=dict, blank=True)
    edited = models.BooleanField(default=False)
    edited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'comments_reply'
        ordering = ['created_at']

    def __str__(self):
        return f"Reply by {self.user.email} to comment {self.comment.id}"

    @property
    def likes(self):
        return self.reactions.filter(reaction_type='like').count()

    @property
    def dislikes(self):
        return self.reactions.filter(reaction_type='dislike').count()

    @property
    def nested_replies(self):
        return self.child_replies.filter(is_active=True).order_by('created_at')


class ReplyReaction(models.Model):
    REACTION_CHOICES = [
        ('like', 'Like'),
        ('dislike', 'Dislike'),
    ]

    user = models.ForeignKey(
        'users.CustomUser',
        on_delete=models.CASCADE,
        related_name='reply_reactions'
    )
    reply = models.ForeignKey(
        Reply,
        on_delete=models.CASCADE,
        related_name='reactions'
    )
    reaction_type = models.CharField(max_length=10, choices=REACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'comments_replyreaction'
        unique_together = ['user', 'reply']

    def __str__(self):
        return f"{self.user.email} {self.reaction_type}d reply {self.reply.id}"
