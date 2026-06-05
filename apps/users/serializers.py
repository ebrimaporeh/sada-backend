from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    is_moderator = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'avatar', 'phone', 'bio', 'region',
            'default_payment_provider', 'default_payment_phone',
            'email_verified', 'is_verified', 'is_moderator', 'created_at',
        ]
        read_only_fields = ['id', 'email', 'role', 'email_verified', 'is_verified', 'created_at']


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone', 'bio', 'region', 'avatar',
            'default_payment_provider', 'default_payment_phone',
        ]


class AdminUserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'avatar', 'phone', 'bio', 'region',
            'default_payment_provider', 'default_payment_phone',
            'is_active', 'email_verified', 'is_verified',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
