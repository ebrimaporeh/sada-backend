from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema
from permissions.base import HasResourceAccess
from permissions.roles import Resource
from .models import VisionTopic
from .serializers import VisionTopicListSerializer, VisionTopicDetailSerializer, AdminVisionTopicSerializer
import services.vision_service as vision_service


class VisionTopicListView(APIView):
    """Public index -- published topics only, lean fields."""
    permission_classes = [AllowAny]

    @extend_schema(summary='List published vision topics', responses={200: VisionTopicListSerializer(many=True)})
    def get(self, request):
        topics = vision_service.get_published_topics()
        serializer = VisionTopicListSerializer(topics, many=True)
        return vision_service.success_response({'topics': serializer.data})


class VisionTopicDetailView(APIView):
    """Public detail by slug -- 404s for a draft or unknown slug, same as
    a draft/rejected campaign isn't reachable at its public URL."""
    permission_classes = [AllowAny]

    @extend_schema(summary='Get a published vision topic', responses={200: VisionTopicDetailSerializer})
    def get(self, request, slug):
        topic = vision_service.get_published_topic(slug)
        serializer = VisionTopicDetailSerializer(topic)
        return vision_service.success_response({'topic': serializer.data})


class AdminVisionTopicListView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.SETTINGS

    @extend_schema(summary='[Admin] List all vision topics', responses={200: AdminVisionTopicSerializer(many=True)})
    def get(self, request):
        topics = vision_service.get_all_topics()
        serializer = AdminVisionTopicSerializer(topics, many=True)
        return vision_service.success_response({'topics': serializer.data})

    @extend_schema(summary='[Admin] Create a vision topic', request=AdminVisionTopicSerializer)
    def post(self, request):
        serializer = AdminVisionTopicSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        topic = vision_service.create_topic(serializer.validated_data)
        out = AdminVisionTopicSerializer(topic)
        return vision_service.success_response({'topic': out.data}, message='Topic created.')


class AdminVisionTopicDetailView(APIView):
    permission_classes = [HasResourceAccess]
    required_resource = Resource.SETTINGS

    @extend_schema(summary='[Admin] Get a vision topic', responses={200: AdminVisionTopicSerializer})
    def get(self, request, slug):
        topic = get_object_or_404(VisionTopic, slug=slug)
        serializer = AdminVisionTopicSerializer(topic)
        return vision_service.success_response({'topic': serializer.data})

    @extend_schema(summary='[Admin] Update a vision topic', request=AdminVisionTopicSerializer)
    def patch(self, request, slug):
        topic = get_object_or_404(VisionTopic, slug=slug)
        serializer = AdminVisionTopicSerializer(topic, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        topic = vision_service.update_topic(topic, serializer.validated_data)
        out = AdminVisionTopicSerializer(topic)
        return vision_service.success_response({'topic': out.data}, message='Topic updated.')

    @extend_schema(summary='[Admin] Delete a vision topic')
    def delete(self, request, slug):
        topic = get_object_or_404(VisionTopic, slug=slug)
        vision_service.delete_topic(topic)
        return vision_service.success_response({}, message='Topic deleted.')
