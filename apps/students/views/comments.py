import logging

from django.db.models import Count
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.students.compat import Enrollment
from apps.students.models import Comment, CommentReaction, Reply, ReplyReaction
from apps.students.serializers import (
    CommentSerializer, CommentCreateSerializer,
    ReplySerializer, ReplyCreateSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Comment views
# ---------------------------------------------------------------------------

class CommentListView(generics.ListAPIView):
    """List comments, optionally filtered by course_id."""
    serializer_class = CommentSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = Comment.objects.filter(is_active=True).select_related(
            'user', 'course'
        ).prefetch_related('replies', 'reactions').order_by('-created_at')
        course_id = self.request.query_params.get('course_id')
        if course_id:
            qs = qs.filter(course_id=course_id)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx


class CommentCreateView(generics.CreateAPIView):
    queryset = Comment.objects.all()
    serializer_class = CommentCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        course_id = request.data.get('course')
        if course_id:
            enrolled = Enrollment.objects.filter(
                student=request.user, course_id=course_id, status__in=['approved', 'completed']
            ).exists()
            if not enrolled:
                return Response(
                    {'error': 'You must be enrolled in the course to comment.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
        try:
            response = super().create(request, *args, **kwargs)
            comment_id = response.data.get('id')
            comment = (
                Comment.objects.get(id=comment_id) if comment_id
                else Comment.objects.filter(user=request.user).order_by('-created_at').first()
            )
            if not comment:
                return Response({'error': 'Comment created but could not retrieve data.'},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            return Response(CommentSerializer(comment, context={'request': request}).data,
                            status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.exception("CommentCreateView error")
            return Response({'error': 'Failed to create comment.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CommentUpdateView(generics.UpdateAPIView):
    """Update own comment content only."""
    queryset = Comment.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Comment.objects.filter(user=self.request.user, is_active=True)

    def update(self, request, *args, **kwargs):
        comment = self.get_object()
        content = request.data.get('content', '').strip()
        if not content:
            return Response({'error': 'Comment content cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(content) > 500:
            return Response({'error': 'Comment cannot exceed 500 characters.'}, status=status.HTTP_400_BAD_REQUEST)
        comment.content = content
        comment.edited = True
        comment.edited_at = timezone.now()
        comment.save()
        return Response(CommentSerializer(comment, context={'request': request}).data)


class CommentDeleteView(generics.DestroyAPIView):
    """Soft-delete own comment."""
    queryset = Comment.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Comment.objects.filter(user=self.request.user)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()

    def destroy(self, request, *args, **kwargs):
        self.perform_destroy(self.get_object())
        return Response({'detail': 'Comment deleted successfully.'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def toggle_comment_reaction(request, comment_id):
    """Toggle like/dislike on a comment."""
    try:
        comment = Comment.objects.get(id=comment_id, is_active=True)
    except Comment.DoesNotExist:
        return Response({'error': 'Comment not found.'}, status=status.HTTP_404_NOT_FOUND)

    reaction_type = request.data.get('reaction_type')
    if reaction_type not in ['like', 'dislike']:
        return Response({'error': 'Invalid reaction type. Use "like" or "dislike".'},
                        status=status.HTTP_400_BAD_REQUEST)

    existing = CommentReaction.objects.filter(user=request.user, comment=comment).first()
    if existing:
        if existing.reaction_type == reaction_type:
            # Remove — toggle off
            existing.delete()
            if reaction_type == 'like':
                comment.likes = max(0, comment.likes - 1)
            else:
                comment.dislikes = max(0, comment.dislikes - 1)
        else:
            # Switch
            old = existing.reaction_type
            existing.reaction_type = reaction_type
            existing.save()
            if old == 'like':
                comment.likes = max(0, comment.likes - 1)
                comment.dislikes += 1
            else:
                comment.dislikes = max(0, comment.dislikes - 1)
                comment.likes += 1
        comment.save()
    else:
        CommentReaction.objects.create(user=request.user, comment=comment, reaction_type=reaction_type)
        if reaction_type == 'like':
            comment.likes += 1
        else:
            comment.dislikes += 1
        comment.save()

    return Response(CommentSerializer(comment, context={'request': request}).data)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def comment_stats(request):
    course_id = request.query_params.get('course_id')
    qs = Comment.objects.filter(is_active=True)
    if course_id:
        qs = qs.filter(course_id=course_id)
    stats = qs.aggregate(total_comments=Count('id'), total_replies=Count('replies'))
    return Response(stats)


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_comments(request):
    comments = Comment.objects.filter(
        user=request.user, is_active=True
    ).select_related('course').order_by('-created_at')
    return Response(CommentSerializer(comments, many=True, context={'request': request}).data)


# ---------------------------------------------------------------------------
# Reply views
# ---------------------------------------------------------------------------

class ReplyCreateView(generics.CreateAPIView):
    queryset = Reply.objects.all()
    serializer_class = ReplyCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        reply_id = response.data.get('id')
        reply = (
            Reply.objects.get(id=reply_id) if reply_id
            else Reply.objects.filter(user=request.user).order_by('-created_at').first()
        )
        return Response(ReplySerializer(reply, context={'request': request}).data, status=status.HTTP_201_CREATED)


class ReplyUpdateView(generics.UpdateAPIView):
    queryset = Reply.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Reply.objects.filter(user=self.request.user, is_active=True)

    def update(self, request, *args, **kwargs):
        reply = self.get_object()
        content = request.data.get('content', '').strip()
        if not content:
            return Response({'error': 'Reply content cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(content) > 500:
            return Response({'error': 'Reply cannot exceed 500 characters.'}, status=status.HTTP_400_BAD_REQUEST)
        reply.content = content
        reply.edited = True
        reply.edited_at = timezone.now()
        reply.save()
        return Response(ReplySerializer(reply, context={'request': request}).data)


class ReplyDeleteView(generics.DestroyAPIView):
    queryset = Reply.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Reply.objects.filter(user=self.request.user)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()

    def destroy(self, request, *args, **kwargs):
        self.perform_destroy(self.get_object())
        return Response({'detail': 'Reply deleted successfully.'}, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def toggle_reply_reaction(request, reply_id):
    """Toggle like/dislike on a reply."""
    try:
        reply = Reply.objects.get(id=reply_id, is_active=True)
    except Reply.DoesNotExist:
        return Response({'error': 'Reply not found.'}, status=status.HTTP_404_NOT_FOUND)

    reaction_type = request.data.get('reaction_type')
    if reaction_type not in ['like', 'dislike']:
        return Response({'error': 'Invalid reaction type. Use "like" or "dislike".'},
                        status=status.HTTP_400_BAD_REQUEST)

    existing = ReplyReaction.objects.filter(user=request.user, reply=reply).first()
    if existing:
        if existing.reaction_type == reaction_type:
            existing.delete()
            detail = f'Removed {reaction_type} from reply'
        else:
            existing.reaction_type = reaction_type
            existing.save()
            detail = f'Changed reaction to {reaction_type}'
    else:
        ReplyReaction.objects.create(user=request.user, reply=reply, reaction_type=reaction_type)
        detail = f'Added {reaction_type} to reply'

    reply.refresh_from_db()
    return Response({'detail': detail, **ReplySerializer(reply, context={'request': request}).data})


class NestedReplyCreateView(generics.CreateAPIView):
    """Create a reply to another reply."""
    queryset = Reply.objects.all()
    serializer_class = ReplyCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        parent_reply_id = request.data.get('parent_reply')
        content = request.data.get('content', '').strip()

        if not parent_reply_id:
            return Response({'error': 'Parent reply ID is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not content:
            return Response({'error': 'Content is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            parent = Reply.objects.get(id=parent_reply_id, is_active=True)
            nested = Reply.objects.create(
                user=request.user,
                comment=parent.comment,
                content=content,
                parent_reply=parent,
            )
            return Response(ReplySerializer(nested, context={'request': request}).data,
                            status=status.HTTP_201_CREATED)
        except Reply.DoesNotExist:
            return Response({'error': 'Parent reply not found.'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.exception("NestedReplyCreateView error")
            return Response({'error': 'Failed to create nested reply.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
