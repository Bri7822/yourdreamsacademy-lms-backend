# core/helpers.py
# Shared utility functions — keep this lean.
# If a helper only serves one app, put it in that app instead.


def get_client_ip(request) -> str:
    """Extract the real client IP, accounting for proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')