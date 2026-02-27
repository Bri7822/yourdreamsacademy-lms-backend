from django.utils import timezone
from student_dashboard.models import GuestSession

class GuestSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Auto-expire guest sessions
        if request.path.startswith('/api/'):
            expired_sessions = GuestSession.objects.filter(
                is_active=True,
                expires_at__lt=timezone.now()
            )
            expired_sessions.update(is_active=False)

            