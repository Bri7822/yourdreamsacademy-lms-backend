# from django.contrib import admin
# from .models import Course, Enrollment, Earnings, Notification

# @admin.register(Course)
# class CourseAdmin(admin.ModelAdmin):
#     list_display = ('title', 'instructor', 'price', 'is_active')
#     list_filter = ('is_active',)
#     search_fields = ('title', 'description', 'instructor__email')

# @admin.register(Enrollment)
# class EnrollmentAdmin(admin.ModelAdmin):
#     list_display = ('student', 'course', 'enrolled_at', 'completed')
#     list_filter = ('completed', 'course')
#     search_fields = ('student__email', 'course__title')

# @admin.register(Earnings)
# class EarningsAdmin(admin.ModelAdmin):
#     list_display = ('instructor', 'course', 'amount', 'date')
#     list_filter = ('date', 'course')
#     search_fields = ('instructor__email', 'course__title')

# @admin.register(Notification)
# class NotificationAdmin(admin.ModelAdmin):
#     list_display = ('recipient', 'is_read', 'created_at')
#     list_filter = ('is_read',)
#     search_fields = ('recipient__email', 'message')