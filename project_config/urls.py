# project_config/urls.py
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # API v1
    path('api/auth/',          include('apps.users.urls')),
    path('api/lessons/',       include('apps.lessons.urls')),
    path('api/quizzes/',       include('apps.quizzes.urls')),
    path('api/subscriptions/', include('apps.subscriptions.urls')),
    path('api/ai/',            include('apps.ai.urls')),
]

# Serve media in development only
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)