from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    verb = serializers.ReadOnlyField()

    class Meta:
        model = AuditLog
        fields = [
            'id', 'actor', 'actor_name', 'actor_email', 'action', 'action_display', 'verb',
            'target_type', 'target_id', 'target_repr',
            'description', 'metadata', 'created_at',
        ]
