# Teacher_dashboard/serializers.py
from rest_framework import serializers
from accounts.models import Course
from admin_dashboard.models import Enrollment

class TeacherCourseSerializer(serializers.ModelSerializer):
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'price', 'duration', 'is_active', 'student_count']
        read_only_fields = ['id', 'student_count']

    def get_student_count(self, obj):
        return obj.enrollments.filter(is_active=True).count()

class TeacherEarningsSerializer(serializers.Serializer):
    total_earnings = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_courses = serializers.IntegerField()

class TeacherEnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    student_email = serializers.EmailField(source='student.user.email', read_only=True)

    class Meta:
        model = Enrollment
        fields = ['id', 'student', 'student_name', 'student_email', 'enrolled_at', 'completed_at', 'is_active']
        read_only_fields = ['id', 'enrolled_at']