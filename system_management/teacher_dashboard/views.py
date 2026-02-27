# Teacher_dashboard/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from accounts.models import Course
from admin_dashboard.models import Lesson, Enrollment
from django.db.models import Sum
from .serializers import (
    TeacherCourseSerializer,
    TeacherEarningsSerializer,
    TeacherEnrollmentSerializer
)

class TeacherPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.profile.user_type == 'teacher'

class TeacherCoursesView(APIView):
    permission_classes = [TeacherPermission]

    def get(self, request):
        courses = Course.objects.filter(teacher=request.user.profile)
        serializer = TeacherCourseSerializer(courses, many=True)
        return Response(serializer.data)

    def post(self, request):
        request.data['teacher'] = request.user.profile.id
        serializer = TeacherCourseSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TeacherEarningsView(APIView):
    permission_classes = [TeacherPermission]

    def get(self, request):
        earnings = Course.objects.filter(teacher=request.user.profile).aggregate(
            total_earnings=Sum('price'),
            total_courses=Count('id')
        )
        serializer = TeacherEarningsSerializer(earnings)
        return Response(serializer.data)

class TeacherEnrollmentsView(APIView):
    permission_classes = [TeacherPermission]

    def get(self, request):
        enrollments = Enrollment.objects.filter(
            course__teacher=request.user.profile
        ).select_related('student', 'course')
        serializer = TeacherEnrollmentSerializer(enrollments, many=True)
        return Response(serializer.data)