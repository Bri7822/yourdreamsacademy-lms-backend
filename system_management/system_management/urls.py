from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from .video_views import video_proxy
from student_dashboard import views as admin_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/admin/', include('admin_dashboard.urls')),
    path('api/teacher/', include('teacher_dashboard.urls')),
    path('api/student/', include('student_dashboard.urls')),

    path('api/search/', admin_views.search_content, name='search-content'),
    path('api/search/public/', admin_views.search_public_content, name='search-public-content'),
    path('api/search/suggestions/', admin_views.search_suggestions, name='search-suggestions'),

    # Enhanced video serving endpoints
    path('media/videos/<path:path>', video_proxy, name='serve-video'),
    path('video-proxy/<path:path>', video_proxy, name='video-proxy'),
]

# Static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

