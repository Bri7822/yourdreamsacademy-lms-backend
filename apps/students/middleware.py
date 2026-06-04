from django.utils import timezone


class GuestSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        """Auto-expire guest sessions on every API request."""
        if request.path.startswith('/api/'):
            from apps.students.models import GuestSession
            GuestSession.objects.filter(
                is_active=True,
                expires_at__lt=timezone.now()
            ).update(is_active=False)
