from django.urls import path
from . import views

urlpatterns = [
    # -------------------------------------------------------------------------
    # Home / public (no auth required)
    # -------------------------------------------------------------------------
    path('home/courses/', views.HomeCourseListView.as_view(), name='home-courses'),
    path('home/courses/<str:course_code>/lessons/', views.HomeCourseLessonsView.as_view(), name='home-course-lessons'),
    path('home/lessons/<int:pk>/', views.HomeLessonDetailView.as_view(), name='home-lesson-detail'),
    path('home/exercises/', views.HomeExercisesView.as_view(), name='home-exercises'),

    # -------------------------------------------------------------------------
    # Dashboard (enrolled users)
    # -------------------------------------------------------------------------
    path('dashboard/courses/', views.DashboardCourseListView.as_view(), name='dashboard-courses'),
    path('dashboard/courses/<str:course_code>/lessons/', views.DashboardCourseLessonsView.as_view(), name='dashboard-course-lessons'),

    # -------------------------------------------------------------------------
    # Courses
    # -------------------------------------------------------------------------
    path('courses/', views.StudentCourseListView.as_view(), name='student-courses'),
    path('courses/public/', views.GuestCourseListView.as_view(), name='public-courses'),
    path('courses/<str:course_code>/', views.StudentCourseDetailView.as_view(), name='student-course-detail'),
    path('courses/<str:course_code>/enroll/', views.enroll_in_course, name='enroll-in-course'),
    path('courses/<str:course_code>/lessons/', views.course_lessons_list, name='course-lessons-list'),
    path('courses/<str:course_code>/lessons/public/', views.public_course_lessons_list, name='course-lessons-public'),

    # -------------------------------------------------------------------------
    # Lessons
    # -------------------------------------------------------------------------
    path('lessons/', views.student_lessons_list, name='student-lessons-list'),
    path('lessons/<int:lesson_id>/', views.student_lesson_detail, name='student-lesson-detail'),
    path('courses/<str:course_slug>/lessons/<str:lesson_slug>/', views.StudentLessonDetailAPIView.as_view(), name='student-lesson-detail-slug'),
    path('lessons/<int:lesson_id>/complete/', views.mark_lesson_completed, name='mark-lesson-completed'),

    # -------------------------------------------------------------------------
    # Exercises & progress
    # -------------------------------------------------------------------------
    path('lessons/<int:lesson_id>/exercises/<str:exercise_id>/submit/', views.submit_exercise_answer, name='submit-exercise-answer'),
    path('lessons/<int:lesson_id>/exercises/<str:exercise_id>/followup/', views.submit_followup_answer, name='submit-followup-answer'),
    path('lessons/<int:lesson_id>/progress/', views.get_exercise_progress, name='exercise-progress'),
    path('lessons/<int:lesson_id>/video-progress/', views.update_video_progress, name='update-video-progress'),
    path('lessons/<int:lesson_id>/video-progress/get/', views.get_video_progress, name='get-video-progress'),

    # -------------------------------------------------------------------------
    # Student stats & exercise lists
    # -------------------------------------------------------------------------
    path('courses-with-exercises/', views.student_courses_with_exercises, name='student-courses-with-exercises'),
    path('grades/summary/', views.student_grades_summary, name='student-grades-summary'),
    path('student-exercises/', views.student_exercises_list, name='student-exercises-list'),
    path('completed-exercises/', views.student_completed_exercises, name='student-completed-exercises'),
    path('pending-exercises/', views.student_pending_exercises, name='student-pending-exercises'),
    path('debug/scores/', views.debug_student_scores, name='debug-scores'),

    # -------------------------------------------------------------------------
    # Guest access
    # -------------------------------------------------------------------------
    path('guest/session/start/', views.start_guest_session, name='start-guest-session'),
    path('guest/session/<uuid:session_id>/validate/', views.validate_guest_session, name='validate-guest-session'),
    path('guest/courses/', views.guest_available_courses, name='guest-available-courses'),
    path('guest/courses/<str:course_code>/', views.guest_course_detail, name='guest-course-detail'),
    path('guest/courses/<str:course_code>/detail/', views.GuestCourseDetailView.as_view(), name='guest-course-detail-cbv'),
    path('guest/courses/<str:course_code>/lessons/', views.guest_course_lessons, name='guest-course-lessons'),
    path('guest/courses/<str:course_code>/lessons-list/', views.GuestCourseLessonsView.as_view(), name='guest-course-lessons-cbv'),
    path('guest/courses/<str:course_slug>/lessons/<str:lesson_slug>/', views.get_guest_lesson_by_slug, name='guest-lesson-by-slug'),
    path('guest/lessons/<int:lesson_id>/exercises/<str:exercise_id>/submit/', views.guest_submit_exercise, name='guest-submit-exercise'),

    # -------------------------------------------------------------------------
    # Certificates
    # -------------------------------------------------------------------------
    path('certificates/', views.student_certificates_list, name='student-certificates-list'),
    path('certificates/<uuid:certificate_id>/download/', views.download_certificate, name='download-certificate'),
    path('certificates/<uuid:certificate_id>/view/', views.view_certificate, name='view-certificate'),
    path('courses/<str:course_code>/generate-certificate/', views.generate_certificate, name='generate-certificate'),
    path('courses/<str:course_code>/certificate-eligibility/', views.check_certificate_eligibility, name='check-certificate-eligibility'),

    # -------------------------------------------------------------------------
    # Search
    # -------------------------------------------------------------------------
    path('search/', views.search_content, name='search-content'),
    path('search/public/', views.search_public_content, name='search-public-content'),
    path('search/suggestions/', views.search_suggestions, name='search-suggestions'),

    # -------------------------------------------------------------------------
    # Comments
    # -------------------------------------------------------------------------
    path('comments/', views.CommentListView.as_view(), name='comment-list'),
    path('comments/create/', views.CommentCreateView.as_view(), name='comment-create'),
    path('comments/<int:pk>/update/', views.CommentUpdateView.as_view(), name='comment-update'),
    path('comments/<int:pk>/delete/', views.CommentDeleteView.as_view(), name='comment-delete'),
    path('comments/<int:comment_id>/react/', views.toggle_comment_reaction, name='comment-react'),
    path('comments/stats/', views.comment_stats, name='comment-stats'),
    path('comments/my-comments/', views.user_comments, name='user-comments'),

    # -------------------------------------------------------------------------
    # Replies
    # -------------------------------------------------------------------------
    path('comments/reply/', views.ReplyCreateView.as_view(), name='reply-create'),
    path('replies/<int:pk>/update/', views.ReplyUpdateView.as_view(), name='reply-update'),
    path('replies/<int:pk>/delete/', views.ReplyDeleteView.as_view(), name='reply-delete'),
    path('replies/<int:reply_id>/react/', views.toggle_reply_reaction, name='reply-react'),
    path('replies/nested/', views.NestedReplyCreateView.as_view(), name='nested-reply-create'),

    # -------------------------------------------------------------------------
    # Debug / health
    # -------------------------------------------------------------------------
    path('health/', views.health_check, name='health-check'),
    path('debug/courses/', views.debug_courses, name='debug-courses'),
    path('debug/guest-courses/', views.debug_guest_courses, name='debug-guest-courses'),
    path('test/<str:course_slug>/<str:lesson_slug>/', views.test_lesson, name='test-lesson'),
]
