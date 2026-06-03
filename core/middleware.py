# core/middleware.py
#
# Add to settings MIDDLEWARE list — place AFTER CorsMiddleware:
#
#   MIDDLEWARE = [
#       ...
#       'corsheaders.middleware.CorsMiddleware',
#       'core.middleware.VideoStreamingMiddleware',   # <-- add this
#       ...
#   ]


class VideoStreamingMiddleware:
    """
    Adds correct streaming headers to any video response so browsers
    can seek without re-downloading the entire file.
    Only activates for paths under /media/videos/ or /video-proxy/.
    """

    VIDEO_PATHS = ('/media/videos/', '/video-proxy/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if any(request.path.startswith(p) for p in self.VIDEO_PATHS):
            response.setdefault('Accept-Ranges', 'bytes')
            response.setdefault('Access-Control-Allow-Origin', '*')
            response.setdefault(
                'Access-Control-Expose-Headers',
                'Content-Range, Content-Length, Accept-Ranges'
            )

        return response