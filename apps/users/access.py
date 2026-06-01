# apps/users/permissions.py
#
# Role-based permission classes.
# Use these on any view that needs role gating:
#   permission_classes = [IsAuthenticated, IsTeacher]
#
from rest_framework.permissions import BasePermission


class IsStudent(BasePermission):
    message = "Access restricted to students."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, 'user_profile')
            and request.user.user_profile.user_type == 'student'
        )


class IsTeacher(BasePermission):
    message = "Access restricted to teachers."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, 'user_profile')
            and request.user.user_profile.user_type == 'teacher'
        )


class IsAdminUser(BasePermission):
    message = "Access restricted to administrators."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, 'user_profile')
            and request.user.user_profile.user_type == 'admin'
        )


class IsTeacherOrAdmin(BasePermission):
    message = "Access restricted to teachers and administrators."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if not hasattr(request.user, 'user_profile'):
            return False
        return request.user.user_profile.user_type in ('teacher', 'admin')