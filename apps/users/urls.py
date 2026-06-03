# apps/users/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Users
    path('users/', views.UserManagementView.as_view(), name='user-management'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user-detail'),
    path('users/bulk_actions/', views.BulkUserActionsView.as_view(), name='bulk-user-actions'),

    # Courses
    path('courses/', views.CourseManagementView.as_view(), name='course-management'),
    path('courses/<int:pk>/', views.CourseDetailView.as_view(), name='course-detail'),
    path('courses/bulk_actions/', views.BulkCourseActionsView.as_view(), name='bulk-course-actions'),
    path('teachers/', views.TeacherListView.as_view(), name='teacher-list'),

    # Enrollments
    path('enrollment-management/enrollments/', views.EnrollmentListView.as_view(), name='enrollment-list'),
    path('enrollment-management/courses/', views.CourseListView.as_view(), name='course-list'),
    path('enrollment-management/statistics/', views.EnrollmentStatisticsView.as_view(), name='enrollment-statistics'),
    path('enrollment-management/auto-approval/', views.AutoApprovalSettingsView.as_view(), name='auto-approval-settings'),
    path('enrollment-management/enrollments/<int:pk>/<str:action>/', views.EnrollmentActionView.as_view(), name='enrollment-action'),
    path('enrollment-management/enrollments/<int:pk>/details/', views.EnrollmentProgressDetailView.as_view(), name='enrollment-progress-detail'),
    path('enrollment-management/bulk-actions/', views.BulkEnrollmentActionsView.as_view(), name='bulk-enrollment-actions'),
    path('enrollment-management/students/', views.StudentListView.as_view(), name='student-list'),
    path('enrollment-management/create-enrollment/', views.EnrollmentCreateView.as_view(), name='create-enrollment'),

    # Dashboard
    path('dashboard/stats/', views.DashboardStatisticsView.as_view(), name='dashboard-statistics'),
]