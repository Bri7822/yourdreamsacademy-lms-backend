# project_config/urls.py
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

urlpatterns = [

    # API v1
    path('api/auth/',          include('apps.users.auth_urls')),
    path('api/lessons/',       include('apps.lessons.urls')),
    path('api/quizzes/',       include('apps.quizzes.urls')),
    path('api/subscriptions/', include('apps.subscriptions.urls')),
    path('api/ai/',            include('apps.ai.urls')),
    
    path('admin/', admin.site.urls),
    path('api/admin/', include('apps.users.urls')),
    path('api/admin/', include('apps.lessons.urls')),
    path('api/admin/', include('apps.subscriptions.urls')),
    
 
    # ── Video proxy ───────────────────────────────────────────────────────
    # path('media/videos/<path:path>', include('core.video_urls')),
    
    
]

# Serve media in development only
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    
