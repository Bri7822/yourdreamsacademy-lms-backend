from django.urls import path
from .views import CreatePaymentView, CapturePaymentView, generate_test_transactions, clear_test_transactions

from .views import (
    LessonListCreateView,
    LessonRetrieveUpdateDestroyView,
    LessonReorderView,  BulkLessonActionsView,
)
from . import views

urlpatterns = [
    path('users/', views.UserManagementView.as_view(), name='user-management'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
    path('users/bulk_actions/', views.BulkUserActionsView.as_view(), name='bulk-user-actions'),
    path('courses/', views.CourseManagementView.as_view(), name='course-management'),
    path('courses/<int:pk>/', views.CourseDetailView.as_view(), name='course-detail'),
    path('courses/bulk_actions/', views.BulkCourseActionsView.as_view(), name='bulk-course-actions'),
    path('teachers/', views.TeacherListView.as_view(), name='teacher-list'),
    path('courses/<int:course_id>/lessons/', LessonListCreateView.as_view(), name='lesson-list-create'),
    path('courses/<int:course_id>/lessons/<int:id>/', LessonRetrieveUpdateDestroyView.as_view(), name='lesson-retrieve-update-destroy'),
    path('courses/<int:course_id>/lessons/reorder/', LessonReorderView.as_view(),  name='lesson-reorder'),
    path('courses/<int:course_id>/lessons/bulk_actions/', BulkLessonActionsView.as_view(), name='bulk-lesson-actions'),
    path('lessons/<int:lesson_id>/exercise/', views.manage_lesson_exercise, name='lesson-exercise'),

   # Video upload endpoints
    path('courses/<int:course_id>/lessons/<int:lesson_id>/upload-video/', views.upload_lesson_video, name='upload-lesson-video'),
    path('courses/<int:course_id>/lessons/upload-video/', views.upload_lesson_video, name='upload-lesson-video-new'),
    path('courses/<int:course_id>/lessons/<int:lesson_id>/delete-video/', views.delete_lesson_video, name='delete-lesson-video'),

    # Enrollment management endpoints
    path('enrollment-management/enrollments/', views.EnrollmentListView.as_view(), name='enrollment-list'),
    path('enrollment-management/courses/', views.CourseListView.as_view(), name='course-list'),
    path('enrollment-management/statistics/', views.EnrollmentStatisticsView.as_view(), name='enrollment-statistics'),
    path('enrollment-management/auto-approval/', views.AutoApprovalSettingsView.as_view(), name='auto-approval-settings'),
    path('enrollment-management/enrollments/<int:pk>/<str:action>/', views.EnrollmentActionView.as_view(), name='enrollment-action'),
    path('enrollment-management/enrollments/<int:pk>/details/', views.EnrollmentProgressDetailView.as_view(), name='enrollment-progress-detail'),
    path('enrollment-management/bulk-actions/', views.BulkEnrollmentActionsView.as_view(), name='bulk-enrollment-actions'),
    path('enrollment-management/students/', views.StudentListView.as_view(), name='student-list'),
    path('enrollment-management/create-enrollment/', views.EnrollmentCreateView.as_view(), name='create-enrollment'),

    # Revenue analytics URLs
    path('revenue/transactions/', views.TransactionViewSet.as_view({'get': 'list'}), name='revenue-transactions'),
    path('revenue/transactions/<int:pk>/process_refund/', views.TransactionViewSet.as_view({'post': 'process_refund'}), name='process-refund'),
    path('revenue/summary/', views.RevenueReportViewSet.as_view({'get': 'summary'}), name='revenue-summary'),
    # path('revenue/reports/export/', views.export_revenue_report, name='export-revenue-report'),

    # testing
    path('paypal/create-payment/', CreatePaymentView.as_view(), name='create-payment'),
    path('paypal/capture-payment/', CapturePaymentView.as_view(), name='capture-payment'),
    path('test/generate-transactions/', views.generate_test_transactions, name='generate-test-transactions'),
    path('test/clear-transactions/', views.clear_test_transactions, name='clear-test-transactions'),

    # Add to your urlpatterns list
    path('dashboard/stats/', views.DashboardStatisticsView.as_view(), name='dashboard-statistics'),
]
