from django.http import StreamingHttpResponse, Http404, FileResponse
from django.conf import settings
import os
import mimetypes

def file_iterator(file_path, chunk_size=8192):
    """Generator to read file in chunks"""
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            yield chunk

def video_proxy(request, path):
    """Serve video files with proper headers for streaming"""
    video_path = os.path.join(settings.MEDIA_ROOT, 'videos', path)

    if not os.path.exists(video_path):
        raise Http404("Video not found")

    # Get file stats
    file_size = os.path.getsize(video_path)
    content_type, _ = mimetypes.guess_type(video_path)
    if not content_type:
        content_type = 'video/mp4'

    # Handle Range requests for video seeking
    range_header = request.META.get('HTTP_RANGE', '').strip()

    if range_header:
        # Parse range header
        range_match = range_header.replace('bytes=', '').split('-')
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if len(range_match) > 1 and range_match[1] else file_size - 1

        # Open file and seek to start position
        with open(video_path, 'rb') as f:
            f.seek(start)
            chunk_size = end - start + 1
            data = f.read(chunk_size)

        response = StreamingHttpResponse(
            iter([data]),
            status=206,  # Partial Content
            content_type=content_type
        )
        response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        response['Content-Length'] = str(chunk_size)
    else:
        # Full file response
        response = FileResponse(
            open(video_path, 'rb'),
            content_type=content_type
        )
        response['Content-Length'] = str(file_size)

    # Essential headers for video streaming
    response['Accept-Ranges'] = 'bytes'
    response['Access-Control-Allow-Origin'] = 'http://localhost:5173'
    response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Range'
    response['Access-Control-Expose-Headers'] = 'Content-Range, Content-Length, Accept-Ranges'

    return response