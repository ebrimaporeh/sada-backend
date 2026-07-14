from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from apps.users.models import User, Organization


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    account_type = serializers.ChoiceField(
        choices=User.AccountType.choices, required=False, default=User.AccountType.INDIVIDUAL,
    )

    # Organization-only — meaningless for an individual registration, so
    # not required=True here; enforced conditionally in validate() instead.
    organization_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    organization_type = serializers.ChoiceField(choices=Organization.OrgType.choices, required=False, allow_blank=True)
    contact_person_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    phone_2 = serializers.CharField(max_length=20, required=False, allow_blank=True)
    # Optional even for organizations — "can add", not "have to add".
    recovery_email_1 = serializers.EmailField(required=False, allow_blank=True)
    recovery_email_2 = serializers.EmailField(required=False, allow_blank=True)

    def validate(self, data):
        if data['password'] != data.pop('password_confirm'):
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})

        if data.get('account_type') == User.AccountType.ORGANIZATION:
            required = ['organization_name', 'organization_type', 'contact_person_name', 'phone', 'phone_2']
            missing = {f: 'This field is required for an organization account.' for f in required if not data.get(f)}
            if missing:
                raise serializers.ValidationError(missing)
        else:
            # Don't silently accept org-only fields on an individual signup.
            org_only_fields = (
                'organization_name', 'organization_type', 'contact_person_name',
                'phone_2', 'recovery_email_1', 'recovery_email_2',
            )
            for f in org_only_fields:
                data.pop(f, None)
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


class TokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class TokenRefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class GoogleOAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField()

    def validate_id_token(self, value):
        if not value:
            raise serializers.ValidationError('ID token is required.')
        return value
