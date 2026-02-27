# Teacher_dashboard/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('courses/', views.TeacherCoursesView.as_view(), name='teacher-courses'),
    path('earnings/', views.TeacherEarningsView.as_view(), name='teacher-earnings'),
    path('enrollments/', views.TeacherEnrollmentsView.as_view(), name='teacher-enrollments'),
]