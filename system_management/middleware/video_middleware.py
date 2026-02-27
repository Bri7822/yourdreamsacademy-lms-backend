# system_management/video_views.py
import os
import mimetypes
from django.http import FileResponse, HttpResponse, StreamingHttpResponse, Http404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from wsgiref.util import FileWrapper
import re

def parse_range_header(range_header, file_size):
    """Parse Range header and return start and end bytes"""
    if not range_header:
        return 0, file_size - 1

    range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
    if not range_match:
        return 0, file_size - 1

    start = int(range_match.group(1))
    end = range_match.group(2)
    end = int(end) if end else file_size - 1

    return start, min(end, file_size - 1)

def file_iterator(file_path, chunk_size=8192, start=0, end=None):
    """Generator to stream file in chunks"""
    with open(file_path, 'rb') as f:
        f.seek(start)
        remaining = end - start + 1 if end else None

        while True:
            chunk_size_to_read = min(chunk_size, remaining) if remaining else chunk_size
            data = f.read(chunk_size_to_read)
            if not data:
                break
            if remaining:
                remaining -= len(data)
            yield data
            if remaining is not None and remaining <= 0:
                break

@csrf_exempt
@require_http_methods(["GET", "HEAD", "OPTIONS"])
def serve_video(request, path):
    """Serve video files with proper streaming support"""

    # Handle preflight OPTIONS request
    if request.method == "OPTIONS":
        response = HttpResponse()
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Range, Accept-Encoding, Authorization"
        response["Access-Control-Expose-Headers"] = "Content-Range, Content-Length, Accept-Ranges"
        return response

    # Get video file path
    from django.conf import settings
    file_path = os.path.join(settings.MEDIA_ROOT, 'videos', path)

    if not os.path.exists(file_path):
        raise Http404("Video not found")

    # Get file size
    file_size = os.path.getsize(file_path)

    # Determine content type
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = 'video/mp4'

    # Handle Range requests
    range_header = request.META.get('HTTP_RANGE', '')

    if range_header:
        start, end = parse_range_header(range_header, file_size)
        length = end - start + 1

        response = StreamingHttpResponse(
            file_iterator(file_path, start=start, end=end),
            status=206,
            content_type=content_type
        )
        response['Content-Length'] = str(length)
        response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
    else:
        # Serve entire file
        response = StreamingHttpResponse(
            file_iterator(file_path),
            content_type=content_type
        )
        response['Content-Length'] = str(file_size)

    # Add headers for video streaming
    response['Accept-Ranges'] = 'bytes'
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Range, Accept-Encoding, Authorization'
    response['Access-Control-Expose-Headers'] = 'Content-Range, Content-Length, Accept-Ranges'
    response['Cache-Control'] = 'public, max-age=3600'

    return response

@csrf_exempt
@require_http_methods(["GET", "HEAD", "OPTIONS"])
def video_proxy(request, path):
    """Alternative video serving endpoint with proxy support"""
    return serve_video(request, path)