from rest_framework import serializers
from permissions.roles import ALL_RESOURCES


class RoleResourcesUpdateSerializer(serializers.Serializer):
    resources = serializers.ListField(child=serializers.CharField(), allow_empty=True)

    def validate_resources(self, value):
        unknown = set(value) - ALL_RESOURCES
        if unknown:
            raise serializers.ValidationError(f'Unknown resource(s): {", ".join(sorted(unknown))}')
        return value
