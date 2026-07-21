from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework import status


def success_response(data, message='Success.', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'message': message, 'data': data}, status=status_code)


def error_response(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': message, 'errors': errors or {}}, status=status_code)


def get_published_topics():
    from apps.vision.models import VisionTopic
    return VisionTopic.objects.filter(is_published=True)


def get_published_topic(slug):
    from apps.vision.models import VisionTopic
    return get_object_or_404(VisionTopic, slug=slug, is_published=True)


def get_all_topics():
    from apps.vision.models import VisionTopic
    return VisionTopic.objects.all()


def create_topic(validated_data):
    from apps.vision.models import VisionTopic
    return VisionTopic.objects.create(**validated_data)


def update_topic(topic, validated_data):
    for field, value in validated_data.items():
        setattr(topic, field, value)
    topic.save()
    return topic


def delete_topic(topic):
    topic.delete()
