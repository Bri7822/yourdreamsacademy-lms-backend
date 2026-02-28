from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db.models.signals import post_save
from .models import CustomUser, UserProfile, create_user_profile

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0          # ← No blank extra forms
    max_num = 1        # ← Only ever ONE profile per user

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('email', 'first_name', 'last_name', 'is_active', 'is_staff')
    list_filter = ('is_active', 'is_staff')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2'),
        }),
    )
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
    inlines = (UserProfileInline,)
    
    def save_model(self, request, obj, form, change):
        # Disconnect signal so the inline handles profile creation, not the signal
        post_save.disconnect(create_user_profile, sender=CustomUser)
        super().save_model(request, obj, form, change)
        post_save.connect(create_user_profile, sender=CustomUser)

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(UserProfile)
