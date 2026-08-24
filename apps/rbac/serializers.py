from rest_framework import serializers
from permissions.roles import ALL_RESOURCES


class RoleResourcesUpdateSerializer(serializers.Serializer):
    resources = serializers.ListField(child=serializers.CharField(), allow_empty=True)

    def validate_resources(self, value):
        unknown = set(value) - ALL_RESOURCES
        if unknown:
            raise serializers.ValidationError(f'Unknown resource(s): {", ".join(sorted(unknown))}')
        return value


class RoleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)
    resources = serializers.ListField(child=serializers.CharField(), required=False, allow_empty=True)

    def validate_name(self, value):
        from apps.rbac.models import Role
        value = value.strip()
        if not value:
            raise serializers.ValidationError('Role name is required.')
        if Role.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError('A role with this name already exists.')
        return value

    def validate_resources(self, value):
        unknown = set(value) - ALL_RESOURCES
        if unknown:
            raise serializers.ValidationError(f'Unknown resource(s): {", ".join(sorted(unknown))}')
        return value
