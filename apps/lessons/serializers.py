from rest_framework import serializers
from .models import Lesson


class LessonSerializer(serializers.ModelSerializer):
    exercise = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = Lesson
        fields = [
            'id', 'title', 'order', 'description', 'content',
            'video_url', 'is_active', 'created_at', 'updated_at',
            'exercise', 'duration', 'video_source', 'video_format',
            'video_duration', 'video_file_size', 'supports_streaming',
            'requires_authentication', 'allow_download', 'video_requirements',
        ]
        read_only_fields = ('id', 'created_at', 'updated_at', 'course')
        extra_kwargs = {
            'exercise': {'required': False, 'allow_null': True},
        }

    def validate_order(self, value):
        if value < 1:
            raise serializers.ValidationError("Order must be at least 1")
        return value

    def validate(self, data):
        # Allow any video URL format — the upload endpoint handles stricter validation
        return data