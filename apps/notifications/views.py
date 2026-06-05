from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from pagination.base import SmallResultsPagination
from .serializers import NotificationSerializer
import services.notification_service as notification_service


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='List my notifications', responses={200: NotificationSerializer(many=True)})
    def get(self, request):
        notifications = notification_service.get_user_notifications(request.user)
        paginator = SmallResultsPagination()
        page = paginator.paginate_queryset(notifications, request)
        serializer = NotificationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Mark notification as read')
    def post(self, request, pk):
        notification_service.mark_read(request.user, pk)
        return notification_service.success_response({}, message='Marked as read.')


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Mark all notifications as read')
    def post(self, request):
        notification_service.mark_all_read(request.user)
        return notification_service.success_response({}, message='All notifications marked as read.')


class UnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary='Get unread notification count')
    def get(self, request):
        count = notification_service.get_unread_count(request.user)
        return notification_service.success_response({'unread_count': count})
