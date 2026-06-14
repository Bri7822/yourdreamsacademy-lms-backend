# apps/users/serializers.py
from django.contrib.auth import authenticate
from rest_framework import serializers

from .models import CustomUser, UserProfile, Course, Enrollment, AutoApprovalSettings


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['user_type', 'terms_agreed', 'bio', 'profile_picture', 'phone_number']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(source='user_profile', read_only=True)

    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'is_active', 'date_joined', 'profile']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, style={'input_type': 'password'})
    user_type = serializers.ChoiceField(choices=['student', 'teacher'], default='student')
    terms_agreed = serializers.BooleanField()

    class Meta:
        model = CustomUser
        fields = ['email', 'first_name', 'last_name', 'password', 'password2', 'user_type', 'terms_agreed']

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password': "Passwords do not match."})
        if not data['terms_agreed']:
            raise serializers.ValidationError({'terms_agreed': "You must agree to the terms and conditions."})
        return data

    def validate_email(self, value):
        if CustomUser.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    # NOTE: No create() here — UserService.register() handles user creation.
    # The serializer's only job is validation.


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(style={'input_type': 'password'})

    def validate(self, data):
        user = authenticate(
            request=self.context.get('request'),
            username=data['email'],
            password=data['password'],
        )
        if not user:
            raise serializers.ValidationError('Invalid email or password.')
        if not user.is_active:
            raise serializers.ValidationError('Account not verified. Please check your email.')

        data['user'] = user
        return data
    
class TeacherSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.CharField(source='user.email')
 
    class Meta:
        model = UserProfile
        fields = ['id', 'name', 'email', 'user_type']
 
    def get_name(self, obj):
        return obj.user.get_full_name()
 
 
class CourseSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(
        source='teacher.user.get_full_name', read_only=True, required=False
    )
    teacher_email = serializers.CharField(
        source='teacher.user.email', read_only=True, required=False
    )
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
 
    class Meta:
        model = Course
        fields = '__all__'
        extra_kwargs = {'teacher': {'required': False}}
 
    def validate(self, data):
        if 'price' in data and data['price'] is not None and data['price'] < 0:
            raise serializers.ValidationError("Price cannot be negative")
        return data
 
 
class EnrollmentCourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['id', 'title', 'code']
 
 
class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    total_enrollments = serializers.SerializerMethodField()
    completed_courses = serializers.SerializerMethodField()
 
    class Meta:
        model = CustomUser
        fields = ['id', 'first_name', 'last_name', 'email',
                  'full_name', 'total_enrollments', 'completed_courses']
 
    def get_full_name(self, obj):
        return obj.get_full_name()
 
    def get_total_enrollments(self, obj):
        return obj.enrollments.count()
 
    def get_completed_courses(self, obj):
        return obj.enrollments.filter(status='completed').count()
 
 
class EnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_email = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)
    exercises_completed = serializers.SerializerMethodField()
    exercises_total = serializers.SerializerMethodField()
 
    class Meta:
        model = Enrollment
        fields = [
            'id', 'student', 'student_name', 'student_email',
            'course', 'course_title', 'course_code', 'status',
            'enrolled_at', 'completed_at', 'progress',
            'exercises_completed', 'exercises_total', 'notes',
        ]
 
    def get_student_name(self, obj):
        return obj.student.get_full_name()
 
    def get_student_email(self, obj):
        return obj.student.email
 
    def get_exercises_completed(self, obj):
        from apps.students.models import StudentExercise
        return StudentExercise.objects.filter(
            student=obj.student, lesson__course=obj.course, completed=True
        ).count()
 
    def get_exercises_total(self, obj):
        from apps.lessons.models import Lesson
        return Lesson.objects.filter(course=obj.course).count()
 
 
class EnrollmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Enrollment
        fields = ['student', 'course', 'status', 'notes']
 
    def validate_student(self, value):
        if not hasattr(value, 'user_profile'):
            raise serializers.ValidationError("Selected user has no profile")
        if value.user_profile.user_type != 'student':
            raise serializers.ValidationError("Selected user is not a student")
        return value
 
    def validate_course(self, value):
        if not value.is_active:
            raise serializers.ValidationError("Course is not active")
        return value
 
    def validate(self, data):
        student, course = data.get('student'), data.get('course')
        if student and course:
            if Enrollment.objects.filter(student=student, course=course).exists():
                raise serializers.ValidationError("Student is already enrolled in this course")
        return data
 
 
class AutoApprovalSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutoApprovalSettings
        fields = ['enabled']    