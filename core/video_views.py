# core/video_views.py
#
# Consolidated video serving — handles Range requests for seeking,
# CORS headers for the Vite dev server, and OPTIONS preflight.

import os
import re
import mimetypes

from django.conf import settings
from django.http import FileResponse, HttpResponse, StreamingHttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_range_header(range_header: str, file_size: int):
    """Return (start, end) byte positions from an HTTP Range header."""
    if not range_header:
        return 0, file_size - 1

    match = re.match(r'bytes=(\d+)-(\d*)', range_header)
    if not match:
        return 0, file_size - 1

    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else file_size - 1
    return start, min(end, file_size - 1)


def file_iterator(file_path: str, chunk_size: int = 8192, start: int = 0, end: int = None):
    """Stream a file in chunks, optionally within a byte range."""
    with open(file_path, 'rb') as f:
        f.seek(start)
        remaining = (end - start + 1) if end is not None else None

        while True:
            to_read = min(chunk_size, remaining) if remaining is not None else chunk_size
            data = f.read(to_read)
            if not data:
                break
            yield data
            if remaining is not None:
                remaining -= len(data)
                if remaining <= 0:
                    break


def _cors_headers(response, origin: str = '*'):
    response['Accept-Ranges'] = 'bytes'
    response['Access-Control-Allow-Origin'] = origin
    response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Range, Accept-Encoding, Authorization'
    response['Access-Control-Expose-Headers'] = 'Content-Range, Content-Length, Accept-Ranges'
    response['Cache-Control'] = 'public, max-age=3600'
    return response


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(["GET", "HEAD", "OPTIONS"])
def serve_video(request, path):
    """Stream a video file from MEDIA_ROOT/videos/ with Range support."""

    # CORS preflight
    if request.method == "OPTIONS":
        return _cors_headers(HttpResponse())

    file_path = os.path.join(settings.MEDIA_ROOT, 'videos', path)
    if not os.path.exists(file_path):
        raise Http404("Video not found")

    file_size = os.path.getsize(file_path)
    content_type, _ = mimetypes.guess_type(file_path)
    content_type = content_type or 'video/mp4'

    range_header = request.META.get('HTTP_RANGE', '')

    if range_header:
        start, end = parse_range_header(range_header, file_size)
        length = end - start + 1
        response = StreamingHttpResponse(
            file_iterator(file_path, start=start, end=end),
            status=206,
            content_type=content_type,
        )
        response['Content-Length'] = str(length)
        response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
    else:
        response = StreamingHttpResponse(
            file_iterator(file_path),
            content_type=content_type,
        )
        response['Content-Length'] = str(file_size)

    # Allow Vite dev server specifically in DEBUG, wildcard in prod
    origin = 'http://localhost:5173' if settings.DEBUG else '*'
    return _cors_headers(response, origin)


@csrf_exempt
@require_http_methods(["GET", "HEAD", "OPTIONS"])
def video_proxy(request, path):
    """Alias for serve_video — keeps the /video-proxy/ endpoint working."""
    return serve_video(request, path)