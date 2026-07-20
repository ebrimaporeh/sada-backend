from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from apps.users.models import User


class RegisterSerializer(serializers.Serializer):
    """Deliberately minimal — just enough to create the account. Name
    (individual) and organization profile details (organization) are no
    longer collected here; they're filled in during onboarding after
    signup, via the existing profile/organization update endpoints."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    account_type = serializers.ChoiceField(
        choices=User.AccountType.choices, required=False, default=User.AccountType.INDIVIDUAL,
    )
    # write_only + popped in validate() -- register_user()/create_user()
    # don't take this as a User field, RegisterView records it separately
    # via consent_service once the account actually exists.
    terms_accepted = serializers.BooleanField(write_only=True)

    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError('You must accept the Terms of Service to create an account.')
        return value

    def validate(self, data):
        if data['password'] != data.pop('password_confirm'):
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        data.pop('terms_accepted')
        return data

    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value.lower()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data.pop('new_password_confirm'):
            raise serializers.ValidationError({'new_password_confirm': 'Passwords do not match.'})
        return data


class SetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data.pop('new_password_confirm'):
            raise serializers.ValidationError({'new_password_confirm': 'Passwords do not match.'})
        return data


class RequestPasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()


class TokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class TokenRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class GoogleOAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField()
    # Only consulted when this Google sign-in creates a brand-new account
    # (e.g. from the signup page's account-type toggle) — ignored for an
    # existing user, who keeps whatever account_type they already have.
    account_type = serializers.ChoiceField(choices=User.AccountType.choices, required=False)

    def validate_id_token(self, value):
        if not value:
            raise serializers.ValidationError('ID token is required.')
        return value
