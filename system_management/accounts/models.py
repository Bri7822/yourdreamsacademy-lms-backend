# accounts/models.py
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver

# accounts/models.py
class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
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
        """Ensure every user has a profile"""
        profile, created = UserProfile.objects.get_or_create(user=self)
        return self.user_profile

class UserProfile(models.Model):
    USER_TYPE_CHOICES = [
        ('admin', 'Administrator'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    ]

    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='user_profile')
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)
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
        return f"{self.user.email}'s profile"

@receiver(post_save, sender=CustomUser)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Set user_type based on user status
        if instance.is_superuser:
            user_type = 'admin'
        elif instance.is_staff:
            user_type = 'teacher'
        else:
            user_type = 'student'

        # get_or_create prevents the UNIQUE constraint crash
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={
                'user_type': user_type,
                'terms_agreed': True
            }
        )

# Dashboard-specific models
class Course(models.Model):
    CATEGORY_CHOICES = [
        ('Finance', 'Finance'),
        ('Personal Development', 'Personal Development'),
        ('Business', 'Business'),
        ('Marketing', 'Marketing'),
        ('Department of Education', 'Department of Education'),
    ]

    title = models.CharField(max_length=255)
    code = models.CharField(max_length=7)
    description = models.TextField()
    teacher = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses_taught')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    duration = models.IntegerField(help_text="Duration in weeks", default=4)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Category field - properly integrated
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        default='Personal Development'
    )
    is_popular = models.BooleanField(default=False, null=True, blank=True)
    is_new = models.BooleanField(default=False, null=True, blank=True)
    is_public = models.BooleanField(default=True, null=True, blank=True)

    class Meta:
        db_table = 'courses_course'

    def __str__(self):
        return self.title

    # Add property getters for safe access
    @property
    def safe_is_popular(self):
        return self.is_popular or False

    @property
    def safe_is_new(self):
        return self.is_new or False

    @property
    def display_category(self):
        """Return the display value for category"""
        return dict(self.CATEGORY_CHOICES).get(self.category, 'General')

    @property
    def total_lessons(self):
        """Return total active lessons for this course"""
        return self.lessons.filter(is_active=True).count()

    @property
    def total_students(self):
        """Return total enrolled students"""
        from admin_dashboard.models import Enrollment
        return self.admin_enrollments.filter(status__in=['approved', 'completed']).count()

    @property
    def is_free(self):
        """Check if course is free"""
        return self.price == 0

    @property
    def teacher_name(self):
        """Get teacher's full name safely"""
        if self.teacher and self.teacher.user:
            full_name = f"{self.teacher.user.first_name} {self.teacher.user.last_name}".strip()
            return full_name if full_name else "Instructor"
        return "Instructor"
