# student_dashboard/urls.py
from rest_framework import generics, permissions
from rest_framework.response import Response
from accounts.models import Course
from admin_dashboard.models import Lesson, Enrollment
from django.db.models import Count, Q
from rest_framework.serializers import ModelSerializer
from django.urls import path
from rest_framework.views import APIView
from . import views
from .views import (HomeCourseListView, HomeCourseLessonsView, HomeLessonDetailView, HomeExercisesView,
    DashboardCourseListView, DashboardCourseLessonsView, student_lessons_list, StudentLessonDetailAPIView,
mark_lesson_completed, student_courses_with_exercises, update_video_progress,
get_video_progress, submit_exercise_answer, StudentCourseListView, toggle_reply_reaction, NestedReplyCreateView
)

urlpatterns = [
    # ✅ HOME COMPONENTS APIs (All data - no enrollment required)
    path('home/courses/', HomeCourseListView.as_view(), name='home-courses'),
    path('home/courses/<str:course_code>/lessons/', HomeCourseLessonsView.as_view(), name='home-course-lessons'),
    path('home/lessons/<int:pk>/', HomeLessonDetailView.as_view(), name='home-lesson-detail'),
    path('home/exercises/', HomeExercisesView.as_view(), name='home-exercises'),

    # ✅ DASHBOARD APIs (Enrolled data only)
    path('dashboard/courses/', DashboardCourseListView.as_view(), name='dashboard-courses'),
    path('dashboard/courses/<str:course_code>/lessons/', DashboardCourseLessonsView.as_view(), name='dashboard-course-lessons'),
      # Public courses (no auth required)
    path('courses/public/', views.GuestCourseListView.as_view(), name='public-courses'),
   
    path('courses/', views.StudentCourseListView.as_view(), name='student-courses'),
    path('courses/<str:course_code>/', views.StudentCourseDetailView.as_view(), name='student-course-detail'),
    path('courses/<str:course_code>/enroll/', views.enroll_in_course, name='enroll-in-course'),
    path('courses/<str:course_code>/lessons/', views.course_lessons_list, name='course-lessons-list'),

    # Lesson management
    path('lessons/', views.student_lessons_list, name='student-lessons-list'),
    path('courses/<str:course_slug>/lessons/<str:lesson_slug>/',StudentLessonDetailAPIView.as_view(), name='student-lesson-detail'),
    path('lessons/<int:lesson_id>/complete/', views.mark_lesson_completed, name='mark-lesson-completed'),
    # student_dashboard/urls.py - Add this line
path('lessons/<int:lesson_id>/', views.student_lesson_detail, name='student-lesson-detail'),
    # Exercise and question management
    path('lessons/<int:lesson_id>/exercises/<str:exercise_id>/submit/', views.submit_exercise_answer, name='submit-exercise-answer'),
    path('lessons/<int:lesson_id>/exercises/<str:exercise_id>/followup/', views.submit_followup_answer, name='submit-followup-answer'),
    path('lessons/<int:lesson_id>/progress/', views.get_exercise_progress, name='exercise-progress'),

    # Enhanced video progress tracking
    path('lessons/<int:lesson_id>/video-progress/', views.update_video_progress, name='update-video-progress'),
    path('lessons/<int:lesson_id>/video-progress/get/', views.get_video_progress, name='get-video-progress'),

    # Additional endpoints
    path('courses-with-exercises/', views.student_courses_with_exercises, name='student-courses-with-exercises'),
    path('grades/summary/', views.student_grades_summary, name='student-grades-summary'),
    path('student-exercises/', views.student_exercises_list, name='student-exercises-list'),
    path('completed-exercises/', views.student_completed_exercises, name='student-completed-exercises'),
    path('pending-exercises/', views.student_pending_exercises, name='student-pending-exercises'),
    path('debug/scores/', views.debug_student_scores, name='debug-scores'),

   # Guest access URLs
    path('guest/session/start/', views.start_guest_session, name='start-guest-session'),
    path('guest/session/<uuid:session_id>/validate/', views.validate_guest_session, name='validate-guest-session'),
    path('guest/courses/', views.guest_available_courses, name='guest-available-courses'),
    path('guest/courses/<str:course_code>/', views.guest_course_detail, name='guest-course-detail'),
    path('guest/courses/<str:course_code>/lessons/', views.guest_course_lessons, name='guest-course-lessons'),
    path('guest/lessons/<int:lesson_id>/exercises/<str:exercise_id>/submit/',
         views.guest_submit_exercise, name='guest-submit-exercise'),
    path('health/', views.health_check, name='health-check'),
    path('debug/courses/', views.debug_courses, name='debug-courses'),
    path('debug/guest-courses/', views.debug_guest_courses, name='debug-guest-courses'),
    path('guest/courses/<str:course_code>/detail/', views.GuestCourseDetailView.as_view(), name='guest-course-detail'),
    path('guest/courses/<str:course_code>/lessons/', views.GuestCourseLessonsView.as_view(), name='guest-course-lessons'),
    path('courses/<str:course_code>/enroll/', views.enroll_in_course, name='enroll-in-course'),
    path('guest/courses/<str:course_slug>/lessons/<str:lesson_slug>/',views.get_guest_lesson_by_slug,name='guest-lesson-simple'),
    # Certificate URLs
    path('certificates/', views.student_certificates_list, name='student-certificates-list'),
    path('certificates/<uuid:certificate_id>/download/', views.download_certificate, name='download-certificate'),
    path('certificates/<uuid:certificate_id>/view/', views.view_certificate, name='view-certificate'),
    path('courses/<str:course_code>/generate-certificate/', views.generate_certificate, name='generate-certificate'),
    path('courses/<str:course_code>/certificate-eligibility/', views.check_certificate_eligibility, name='check-certificate-eligibility'),

    path('search/', views.search_content, name='search-content'),
    path('search/public/', views.search_public_content, name='search-public-content'),
    path('search/suggestions/', views.search_suggestions, name='search-suggestions'),

    # Comments APIs
    path('comments/', views.CommentListView.as_view(), name='comment-list'),
    path('comments/create/', views.CommentCreateView.as_view(), name='comment-create'),
    path('comments/reply/', views.ReplyCreateView.as_view(), name='reply-create'),
    path('comments/<int:comment_id>/react/', views.toggle_comment_reaction, name='comment-react'),
    path('comments/stats/', views.comment_stats, name='comment-stats'),
    path('comments/my-comments/', views.user_comments, name='user-comments'),
    # Comment edit/delete endpoints - FIXED URL PATTERNS
    path('comments/<int:pk>/update/', views.CommentUpdateView.as_view(), name='comment-update'),
    path('comments/<int:pk>/delete/', views.CommentDeleteView.as_view(), name='comment-delete'),
    # Reply edit/delete endpoints - FIXED URL PATTERNS
    path('replies/<int:pk>/update/', views.ReplyUpdateView.as_view(), name='reply-update'),
    path('replies/<int:pk>/delete/', views.ReplyDeleteView.as_view(), name='reply-delete'),

    # Reply reactions and nested replies
    path('replies/<int:reply_id>/react/', views.toggle_reply_reaction, name='reply-react'),
    path('replies/nested/', views.NestedReplyCreateView.as_view(), name='nested-reply-create'),

    path('test/<str:course_slug>/<str:lesson_slug>/', views.test_lesson, name='test'),
]