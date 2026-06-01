# core/access.py
#
# Project-wide permission classes.
# Role-specific ones (IsStudent, IsTeacher etc.) live in apps/users/access.py
#
from rest_framework.permissions import BasePermission


class IsOwnerOrAdmin(BasePermission):
    """Allow access if the requesting user owns the object, or is an admin."""

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        profile = getattr(request.user, 'user_profile', None)
        if profile and profile.user_type == 'admin':
            return True
        return getattr(obj, 'user', None) == request.user