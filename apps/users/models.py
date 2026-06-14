from django.db import models

# Create your models here.
# apps/users/models.py
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        db_table = 'accounts_customuser'

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    @property
    def profile(self):
        """Safe profile accessor — always returns a profile."""
        profile, _ = UserProfile.objects.get_or_create(
            user=self,
            defaults={'user_type': self._default_user_type()}
        )
        return profile

    def _default_user_type(self):
        if self.is_superuser:
            return 'admin'
        if self.is_staff:
            return 'teacher'
        return 'student'


class UserProfile(models.Model):
    USER_TYPE_CHOICES = [
        ('admin', 'Administrator'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    ]

    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='user_profile'
    )
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='student')
    terms_agreed = models.BooleanField(default=False)
    bio = models.TextField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_userprofile'

    def __str__(self):
        return f"{self.user.email} ({self.user_type})"

    @property
    def is_student(self):
        return self.user_type == 'student'

    @property
    def is_teacher(self):
        return self.user_type == 'teacher'

    @property
    def is_admin(self):
        return self.user_type == 'admin'


@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    """Auto-create a profile when a new user is created."""
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                'user_type': instance._default_user_type(),
                'terms_agreed': False,
            }
        )
        
# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------
 
class Course(models.Model):
    title = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True, null=True)
    teacher = models.ForeignKey(
        UserProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='courses_taught',
    )
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
 
    class Meta:
        app_label = 'users'
        ordering = ['-created_at']
 
    def __str__(self):
        return self.title
 
 
# ---------------------------------------------------------------------------
# Enrollment
# ---------------------------------------------------------------------------
 
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
 
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
 
    class Meta:
        app_label = 'users'
        unique_together = ('student', 'course')
        ordering = ['-enrolled_at']
 
    def __str__(self):
        return f"{self.student.email} → {self.course.title}"
 
    def clean(self):
        if not hasattr(self.student, 'user_profile'):
            raise ValidationError("Selected user has no profile")
        if self.student.user_profile.user_type != 'student':
            raise ValidationError("Selected user is not a student")
 
    def save(self, *args, **kwargs):
        self.full_clean()
        if self.status == self.COMPLETED and not self.completed_at:
            self.completed_at = timezone.now()
        super().save(*args, **kwargs)
 
    # ---- computed properties ----
 
    @property
    def progress(self):
        from apps.lessons.models import Lesson
        from apps.students.models import StudentExercise
        total = Lesson.objects.filter(course=self.course).count()
        if total == 0:
            return 0
        completed = StudentExercise.objects.filter(
            student=self.student, lesson__course=self.course, completed=True
        ).count()
        return round((completed / total) * 100, 1)

    @property
    def exercises_completed(self):
        from apps.students.models import StudentExercise
        return StudentExercise.objects.filter(
            student=self.student, lesson__course=self.course, completed=True
        ).count()
 
    @property
    def exercises_total(self):
        from apps.lessons.models import Lesson
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
 
 
# ---------------------------------------------------------------------------
# AutoApprovalSettings
# ---------------------------------------------------------------------------
 
class AutoApprovalSettings(models.Model):
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True
    )
 
    class Meta:
        app_label = 'users'
        verbose_name = "Auto Approval Settings"
        verbose_name_plural = "Auto Approval Settings"
 
    def __str__(self):
        return f"Auto-Approval {'Enabled' if self.enabled else 'Disabled'}"        