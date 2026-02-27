
# admin_dashboard/serializers.py
from rest_framework import serializers
from accounts.models import CustomUser, UserProfile, Course
from admin_dashboard.models import (Lesson,
Enrollment, AutoApprovalSettings,Transaction, TeacherPayout, RevenueReport
)
from student_dashboard.models import StudentExercise
import re

class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = ['user_type', 'terms_agreed', 'profile_picture']

# admin_dashboard/serializers.py
class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(source='user_profile')  # Add source here
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'password', 'is_active', 'date_joined', 'profile']
        read_only_fields = ['id', 'date_joined']

    def create(self, validated_data):
        profile_data = validated_data.pop('user_profile', {'user_type': 'student'})  # Changed here
        password = validated_data.pop('password', None)

        user = CustomUser.objects.create(**validated_data)
        if password:
            user.set_password(password)
            user.save()

        UserProfile.objects.create(user=user, **profile_data)
        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('user_profile', {})  # Changed here

        # Update user fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Update profile if data provided
        if profile_data:
            profile = instance.user_profile  # Changed here
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()

        instance.save()
        return instance

    profile = UserProfileSerializer(source='user_profile')
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'password', 'is_active', 'date_joined', 'profile']
        read_only_fields = ['id', 'date_joined']

    def create(self, validated_data):
        # Extract profile data with default student role
        profile_data = validated_data.pop('user_profile', {'user_type': 'student'})
        password = validated_data.pop('password', None)

        # Create user first
        user = CustomUser.objects.create(**validated_data)

        # Set password if provided
        if password:
            user.set_password(password)
            user.save()

        # Create profile through the proper relationship
        UserProfile.objects.create(user=user, **profile_data)

        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('user_profile', {})

        # Update user fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Update profile if data provided
        if profile_data:
            profile = instance.profile
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()

        instance.save()
        return instance
    profile = UserProfileSerializer()
    password = serializers.CharField(write_only=True, required=False)  # 👈 Add this

    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'password', 'is_active', 'date_joined', 'profile']
        read_only_fields = ['id', 'date_joined']

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {})
        profile = instance.profile

        # Update user fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Update profile fields
        for attr, value in profile_data.items():
            setattr(profile, attr, value)

        instance.save()
        profile.save()
        return instance

    # admin_dashboard/serializers.py
    def create(self, validated_data):
        profile_data = validated_data.pop('profile', {'user_type': 'student'})
        password = validated_data.pop('password', None)

        user = CustomUser.objects.create(**validated_data)
        if password:
            user.set_password(password)
            user.save()

        # Create profile only if it doesn't exist
        if not hasattr(user, 'profile'):
            UserProfile.objects.create(user=user, **profile_data)
        else:
            # Update existing profile if needed
            for attr, value in profile_data.items():
                setattr(user.profile, attr, value)
            user.profile.save()

        return user

# course
class CourseSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.user.get_full_name', read_only=True, required=False)
    teacher_email = serializers.CharField(source='teacher.user.email', read_only=True, required=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)

    class Meta:
        model = Course
        fields = '__all__'
        extra_kwargs = {
            'teacher': {'required': False}
        }

    def validate(self, data):
        if 'price' in data and data['price'] is not None:
            if data['price'] < 0:
                raise serializers.ValidationError("Price cannot be negative")
        return data

class TeacherSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    email = serializers.CharField(source='user.email')

    class Meta:
        model = UserProfile
        fields = ['id', 'name', 'email', 'user_type']

    def get_name(self, obj):
        return obj.user.get_full_name()

class LessonSerializer(serializers.ModelSerializer):
    exercise = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = Lesson
        fields = [
            'id',
            'title',
            'order',
            'description',
            'content',
            'video_url',
            'is_active',
            'created_at',
            'updated_at',
            'exercise'
        ]
        read_only_fields = ('id', 'created_at', 'updated_at', 'course')

        extra_kwargs = {
            'exercise': {'required': False, 'allow_null': True}
        }

    def validate_order(self, value):
        if value < 1:
            raise serializers.ValidationError("Order must be at least 1")
        return value

    def validate(self, data):
        """
        Remove overly strict video validation that prevents legitimate uploads
        """
        # Allow any video URL format during editing
        # The upload endpoint handles validation appropriately
        return data

# ================
# Enrollment Serializers
# ================
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
        fields = ['id', 'first_name', 'last_name', 'email', 'full_name', 'total_enrollments', 'completed_courses']

    def get_full_name(self, obj):
        return obj.get_full_name()

    def get_total_enrollments(self, obj):
        return obj.admin_enrollments.count()

    def get_completed_courses(self, obj):
        return obj.admin_enrollments.filter(status='completed').count()


class EnrollmentStudentExerciseSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source='lesson.title', read_only=True)
    description = serializers.CharField(source='lesson.description', read_only=True)

    class Meta:
        model = StudentExercise
        fields = ['id', 'title', 'description', 'completed', 'completed_at', 'score']


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
            'exercises_completed', 'exercises_total', 'notes'
        ]

    def get_student_name(self, obj):
        return obj.student.get_full_name()

    def get_student_email(self, obj):
        return obj.student.email

    def get_exercises_completed(self, obj):
        return StudentExercise.objects.filter(
            student=obj.student,
            lesson__course=obj.course,
            completed=True
        ).count()

    def get_exercises_total(self, obj):
        return Lesson.objects.filter(course=obj.course).count()


class EnrollmentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Enrollment
        fields = ['student', 'course', 'status', 'notes']

    def validate_student(self, value):
        """Validate that the selected user is actually a student"""
        if not hasattr(value, 'user_profile'):
            raise serializers.ValidationError("Selected user has no profile")

        if value.user_profile.user_type != 'student':
            raise serializers.ValidationError("Selected user is not a student")

        return value

    def validate_course(self, value):
        """Validate that the course is active"""
        if not value.is_active:
            raise serializers.ValidationError("Course is not active")

        return value

    def validate(self, data):
        """Check for duplicate enrollment"""
        student = data.get('student')
        course = data.get('course')

        if student and course:
            existing_enrollment = Enrollment.objects.filter(
                student=student,
                course=course
            ).exists()

            if existing_enrollment:
                raise serializers.ValidationError(
                    "Student is already enrolled in this course"
                )

        return data


class AutoApprovalSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutoApprovalSettings
        fields = ['enabled']


class LessonSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lesson
        fields = ['id', 'title', 'order', 'description', 'content', 'video_url', 'is_active', 'exercise']


# revenue
class TransactionSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    teacher_name = serializers.CharField(
        source='teacher.user.get_full_name',
        read_only=True,
        allow_null=True
    )

    class Meta:
        model = Transaction
        fields = [
            'id', 'transaction_id', 'course', 'course_title',
            'student', 'student_name', 'teacher', 'teacher_name',
            'amount', 'currency', 'platform_fee', 'teacher_payout',
            'status', 'payment_gateway', 'gateway_transaction_id',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['transaction_id', 'platform_fee', 'teacher_payout']

class TeacherPayoutSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.user.get_full_name', read_only=True)
    teacher_email = serializers.CharField(source='teacher.user.email', read_only=True)

    class Meta:
        model = TeacherPayout
        fields = [
            'id', 'teacher', 'teacher_name', 'teacher_email',
            'period_start', 'period_end', 'total_sales',
            'platform_commission', 'payout_amount', 'hosting_fee',
            'final_payout', 'status', 'processed_at',
            'created_at', 'updated_at'
        ]

class RevenueReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = RevenueReport
        fields = [
            'id', 'report_type', 'period_start', 'period_end',
            'total_revenue', 'total_transactions', 'average_transaction_value',
            'platform_commission', 'teacher_payouts', 'hosting_fees',
            'net_profit', 'currency_breakdown', 'top_courses',
            'generated_at'
        ]
        