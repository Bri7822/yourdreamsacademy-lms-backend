from django.shortcuts import render
import os
import re
import logging

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from rest_framework import generics, permissions, serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
import django.db.models as dj_models

from apps.lessons.models import Lesson
from apps.lessons.serializers import LessonSerializer

# Course is owned by the users/courses app — import lazily or via string ref in queries
from apps.users.models import Course  # adjust if Course lives elsewhere

logger = logging.getLogger(__name__)


class LessonListCreateView(generics.ListCreateAPIView):
    serializer_class = LessonSerializer
    permission_classes = [permissions.IsAdminUser]

    def get_queryset(self):
        return Lesson.objects.filter(course_id=self.kwargs['course_id']).order_by('order')

    def perform_create(self, serializer):
        course_id = self.kwargs['course_id']
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            raise serializers.ValidationError("Course not found")

        if 'order' not in serializer.validated_data:
            max_order = (
                Lesson.objects.filter(course=course)
                .aggregate(dj_models.Max('order'))['order__max'] or 0
            )
            serializer.validated_data['order'] = max_order + 1

        serializer.save(course=course)


class LessonRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LessonSerializer
    permission_classes = [permissions.IsAdminUser]
    lookup_field = 'id'

    def get_queryset(self):
        return Lesson.objects.filter(course_id=self.kwargs['course_id'])

    def perform_update(self, serializer):
        exercise_data = self.request.data.get('exercise')
        if exercise_data is not None:
            serializer.validated_data['exercise'] = exercise_data
        serializer.save()

    def perform_destroy(self, instance):
        course_id = self.kwargs['course_id']
        deleted_order = instance.order
        try:
            with transaction.atomic():
                instance.delete()
                lessons = Lesson.objects.filter(
                    course_id=course_id, order__gt=deleted_order
                ).order_by('order')
                for lesson in lessons:
                    lesson.order -= 1
                    lesson.save()
        except Exception as e:
            raise serializers.ValidationError({'error': f'Failed to delete lesson: {str(e)}'})

    def put(self, request, course_id, id):
        try:
            lesson = Lesson.objects.get(id=id, course_id=course_id)
            serializer = LessonSerializer(lesson, data=request.data)
            if serializer.is_valid():
                try:
                    serializer.save()
                    return Response(serializer.data)
                except ValidationError as e:
                    return Response({'error': e.message_dict}, status=400)
            return Response(serializer.errors, status=400)
        except Lesson.DoesNotExist:
            return Response({'error': 'Lesson not found'}, status=404)


class BulkLessonActionsView(generics.GenericAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = LessonSerializer

    def post(self, request, course_id):
        action = request.data.get('action')
        lesson_ids = request.data.get('lesson_ids', [])

        if not action or not lesson_ids:
            return Response(
                {'error': 'Action and lesson_ids are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lessons = Lesson.objects.filter(course_id=course_id, id__in=lesson_ids)
        if not lessons.exists():
            return Response(
                {'error': 'No valid lessons found for this course'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if action == 'activate':
            lessons.update(is_active=True)
            return Response({'success': f'{lessons.count()} lessons activated'})
        elif action == 'deactivate':
            lessons.update(is_active=False)
            return Response({'success': f'{lessons.count()} lessons deactivated'})
        elif action == 'delete':
            try:
                with transaction.atomic():
                    to_delete = list(lessons.values('id', 'order'))
                    deleted_count = lessons.count()
                    lessons.delete()
                    for info in to_delete:
                        Lesson.objects.filter(
                            course_id=course_id, order__gt=info['order']
                        ).update(order=dj_models.F('order') - 1)
                return Response({'success': f'{deleted_count} lessons deleted'})
            except Exception as e:
                return Response(
                    {'error': f'Failed to delete lessons: {str(e)}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        return Response(
            {'error': 'Invalid action. Use "activate", "deactivate", or "delete"'},
            status=status.HTTP_400_BAD_REQUEST,
        )


class LessonReorderView(generics.GenericAPIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, course_id):
        lesson_order = request.data.get('order', [])
        if not lesson_order:
            return Response({'error': 'Order list is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                existing = set(
                    Lesson.objects.filter(course_id=course_id).values_list('id', flat=True)
                )
                if set(lesson_order) != existing:
                    return Response(
                        {'error': 'Lesson IDs do not match course lessons'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                for index, lesson_id in enumerate(lesson_order, start=1):
                    Lesson.objects.filter(id=lesson_id).update(order=index)
            return Response({'status': 'success'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST', 'PUT'])
@permission_classes([IsAdminUser])
def manage_lesson_exercise(request, lesson_id):
    try:
        lesson = Lesson.objects.get(id=lesson_id)
    except Lesson.DoesNotExist:
        return Response({'error': 'Lesson not found'}, status=404)

    exercise_data = {
        'paragraph': request.data.get('paragraph'),
        'fill_blank': request.data.get('fill_blank'),
        'multiple_choice': request.data.get('multiple_choice'),
    }
    exercise_data = {k: v for k, v in exercise_data.items() if v is not None}

    if not exercise_data:
        return Response({'error': 'No exercise data provided'}, status=400)

    lesson.exercise = exercise_data
    lesson.save()
    return Response({'exercise': lesson.exercise}, status=200 if request.method == 'PUT' else 201)


@api_view(['POST'])
@permission_classes([IsAdminUser])
def upload_lesson_video(request, course_id, lesson_id=None):
    try:
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=404)

        lesson = None
        if lesson_id:
            try:
                lesson = Lesson.objects.get(id=lesson_id, course=course)
            except Lesson.DoesNotExist:
                return Response({'error': 'Lesson not found'}, status=404)

        video_url = request.data.get('video_url', '').strip()
        video_file = request.FILES.get('video')

        if not video_url and not video_file:
            return Response({'error': 'Either video URL or video file must be provided'}, status=400)
        if video_url and video_file:
            return Response({'error': 'Cannot provide both URL and file upload'}, status=400)

        # ---- URL path ----
        if video_url:
            if not (
                video_url.startswith(('http://', 'https://', 'videos/'))
                or any(d in video_url for d in ['youtube', 'youtu.be', 'vimeo'])
            ):
                return Response({'error': 'Please enter a valid video URL or upload a file'}, status=400)

            # Normalise to embed URLs
            if 'youtube.com/watch' in video_url:
                video_id = video_url.split('v=')[1].split('&')[0]
                video_url = f'https://www.youtube.com/embed/{video_id}'
            elif 'youtu.be' in video_url:
                video_id = video_url.split('youtu.be/')[1].split('?')[0]
                video_url = f'https://www.youtube.com/embed/{video_id}'
            elif 'vimeo.com' in video_url and 'player.vimeo.com' not in video_url:
                video_id = video_url.split('vimeo.com/')[1].split('?')[0]
                video_url = f'https://player.vimeo.com/video/{video_id}'

            if lesson:
                if lesson.video_url and lesson.video_url.startswith('videos/'):
                    old_path = os.path.join(settings.MEDIA_ROOT, lesson.video_url)
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except OSError:
                            pass
                try:
                    lesson.video_url = video_url
                    lesson.full_clean()
                    lesson.save()
                except ValidationError as e:
                    return Response({'error': e.message_dict}, status=400)

            return Response({
                'video_url': video_url,
                'type': 'url',
                'message': 'Video URL saved successfully',
                'id': lesson.id if lesson else None,
            }, status=201)

        # ---- File upload path ----
        if video_file:
            valid_ext = ['.mp4', '.webm', '.ogg']
            ext = os.path.splitext(video_file.name)[1].lower()
            if ext not in valid_ext:
                return Response(
                    {'error': f'Invalid format. Supported: {", ".join(valid_ext)}'}, status=400
                )
            if video_file.size > 100 * 1024 * 1024:
                return Response({'error': 'File too large. Maximum size is 100MB'}, status=400)

            upload_dir = os.path.join('videos', f'course_{course_id}')
            if lesson_id:
                upload_dir = os.path.join(upload_dir, f'lesson_{lesson_id}')
            full_upload_path = os.path.join(settings.MEDIA_ROOT, upload_dir)
            os.makedirs(full_upload_path, exist_ok=True)

            timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
            clean_name = re.sub(r'[^\w\-_\.]', '_', video_file.name)
            filename = f"{timestamp}_{clean_name}"

            fs = FileSystemStorage(location=full_upload_path)
            saved_name = fs.save(filename, video_file)
            video_url = os.path.join(upload_dir, saved_name).replace('\\', '/')
            full_url = request.build_absolute_uri(settings.MEDIA_URL + video_url)

            if lesson:
                if lesson.video_url and lesson.video_url.startswith('videos/'):
                    old_path = os.path.join(settings.MEDIA_ROOT, lesson.video_url)
                    if os.path.exists(old_path):
                        try:
                            os.remove(old_path)
                        except OSError:
                            pass
                try:
                    lesson.video_url = video_url
                    lesson.full_clean()
                    lesson.save()
                except ValidationError as e:
                    fs.delete(saved_name)
                    return Response({'error': e.message_dict}, status=400)

            return Response({
                'video_url': video_url,
                'full_url': full_url,
                'filename': saved_name,
                'size': video_file.size,
                'type': 'file',
                'message': 'Video uploaded successfully',
                'id': lesson.id if lesson else None,
            }, status=201)

    except Exception as e:
        logger.error(f"Video upload failed: {str(e)}", exc_info=True)
        return Response({'error': 'Failed to process video. Please try again.'}, status=500)


@api_view(['DELETE'])
@permission_classes([IsAdminUser])
def delete_lesson_video(request, course_id, lesson_id):
    try:
        lesson = Lesson.objects.get(id=lesson_id, course_id=course_id)
        if lesson.video_url:
            video_path = os.path.join(settings.MEDIA_ROOT, lesson.video_url)
            if os.path.exists(video_path):
                os.remove(video_path)
            lesson.video_url = ''
            lesson.save()
            return Response({'message': 'Video deleted successfully'})
        return Response({'error': 'No video to delete'}, status=404)
    except Lesson.DoesNotExist:
        return Response({'error': 'Lesson not found'}, status=404)
    except Exception as e:
        logger.error(f"Video delete failed: {str(e)}", exc_info=True)
        return Response({'error': 'Failed to delete video'}, status=500)
