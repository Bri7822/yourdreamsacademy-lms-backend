"""
Centralised import map for cross-app models.
Correct locations confirmed via manage.py shell inspection.
"""

# ── apps.users ───────────────────────────────────────────────────────────────
# CustomUser, Course, UserProfile, Enrollment all live here
from apps.users.models import CustomUser, Course, UserProfile, Enrollment  # noqa: F401

# ── apps.lessons ─────────────────────────────────────────────────────────────
# Lesson, LessonProgress, VideoAnalytics live here (NO Enrollment here)
from apps.lessons.models import Lesson, LessonProgress  # noqa: F401
try:
    from apps.lessons.models import VideoAnalytics  # noqa: F401
except ImportError:
    VideoAnalytics = None

__all__ = [
    "CustomUser",
    "Course",
    "UserProfile",
    "Enrollment",
    "Lesson",
    "LessonProgress",
    "VideoAnalytics",
]
