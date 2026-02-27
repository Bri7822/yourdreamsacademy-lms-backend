from django.contrib import admin
from .models import GuestSession, GuestAccessSettings

@admin.register(GuestSession)
class GuestSessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'created_at', 'expires_at', 'is_active', 'time_used', 'get_remaining_time']
    list_filter = ['is_active', 'created_at']
    readonly_fields = ['session_id', 'created_at']
    search_fields = ['session_id']

    def get_remaining_time(self, obj):
        return obj.get_time_remaining_display()
    get_remaining_time.short_description = 'Remaining Time'

@admin.register(GuestAccessSettings)
class GuestAccessSettingsAdmin(admin.ModelAdmin):
    list_display = ['enabled', 'max_session_time', 'max_lessons_access']
    filter_horizontal = ['allowed_courses']

    def has_add_permission(self, request):
        return not GuestAccessSettings.objects.exists()