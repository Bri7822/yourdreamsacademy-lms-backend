# apps/lessons/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Lesson CRUD
    path(
        'courses/<int:course_id>/lessons/',
        views.LessonListCreateView.as_view(),
        name='lesson-list-create',
    ),
    path(
        'courses/<int:course_id>/lessons/<int:id>/',
        views.LessonRetrieveUpdateDestroyView.as_view(),
        name='lesson-detail',
    ),
    path(
        'courses/<int:course_id>/lessons/reorder/',
        views.LessonReorderView.as_view(),
        name='lesson-reorder',
    ),
    path(
        'courses/<int:course_id>/lessons/bulk_actions/',
        views.BulkLessonActionsView.as_view(),
        name='bulk-lesson-actions',
    ),

    # Exercise management
    path(
        'lessons/<int:lesson_id>/exercise/',
        views.manage_lesson_exercise,
        name='lesson-exercise',
    ),

    # Video management
    path(
        'courses/<int:course_id>/lessons/<int:lesson_id>/upload-video/',
        views.upload_lesson_video,
        name='upload-lesson-video',
    ),
    path(
        'courses/<int:course_id>/lessons/upload-video/',
        views.upload_lesson_video,
        name='upload-lesson-video-new',
    ),
    path(
        'courses/<int:course_id>/lessons/<int:lesson_id>/delete-video/',
        views.delete_lesson_video,
        name='delete-lesson-video',
    ),
]