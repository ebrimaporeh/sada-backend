from rest_framework import serializers
from .models import User, IdentityVerification, Organization, OrganizationVerification


class OrganizationSerializer(serializers.ModelSerializer):
    """Read-only for now — organization_name/organization_type are tied to
    what was (or will be) verified, so editing them post-registration is
    deliberately out of scope until the verification flow exists."""
    logo = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'organization_name', 'organization_type', 'contact_person_name',
            'phone_2', 'recovery_email_1', 'recovery_email_2', 'logo',
        ]

    def get_logo(self, obj):
        request = self.context.get('request')
        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)
        return None


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    is_moderator = serializers.ReadOnlyField()
    is_google_linked = serializers.ReadOnlyField()
    avatar = serializers.SerializerMethodField()
    has_usable_password = serializers.SerializerMethodField()
    organization = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'account_type', 'organization', 'avatar', 'phone', 'bio', 'region',
            'default_payment_provider', 'default_payment_phone',
            'email_verified', 'is_verified', 'is_moderator', 'created_at',
            'show_total_raised',
            'notify_donations_received', 'notify_campaign_approved', 'notify_campaign_rejected',
            'notify_goal_reached', 'notify_new_comment', 'notify_new_update', 'notify_marketing',
            'has_usable_password', 'is_google_linked',
        ]
        read_only_fields = ['id', 'email', 'role', 'account_type', 'email_verified', 'is_verified', 'created_at']

    def get_avatar(self, obj):
        request = self.context.get('request')
        if obj.avatar and request:
            return request.build_absolute_uri(obj.avatar.url)
        return None

    def get_has_usable_password(self, obj):
        return obj.has_usable_password()

    def get_organization(self, obj):
        org = getattr(obj, 'organization', None)
        if org is None:
            return None
        return OrganizationSerializer(org, context=self.context).data


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'phone', 'bio', 'region', 'avatar',
            'default_payment_provider', 'default_payment_phone', 'show_total_raised',
            'notify_donations_received', 'notify_campaign_approved', 'notify_campaign_rejected',
            'notify_goal_reached', 'notify_new_comment', 'notify_new_update', 'notify_marketing',
        ]


class AdminUserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name',
            'role', 'avatar', 'phone', 'bio', 'region',
            'default_payment_provider', 'default_payment_phone',
            'is_active', 'email_verified', 'is_verified',
            'notify_donations_received', 'notify_campaign_approved', 'notify_campaign_rejected',
            'notify_goal_reached', 'notify_new_comment', 'notify_new_update', 'notify_marketing',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_avatar(self, obj):
        request = self.context.get('request')
        if obj.avatar and request:
            return request.build_absolute_uri(obj.avatar.url)
        return None


class AdminUserCreateSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=[User.Role.MODERATOR, User.Role.FINANCE_OFFICER])

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'phone', 'role']

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value


class PublicCampaignerSerializer(serializers.ModelSerializer):
    """A campaign owner's public profile — deliberately minimal. Never add
    email, phone, role, payment fields, or anything from IdentityVerification
    here; is_verified is the only verification-related field ever exposed
    publicly (just the badge, never the underlying ID submission)."""
    full_name = serializers.ReadOnlyField()
    avatar = serializers.SerializerMethodField()
    campaign_count = serializers.IntegerField(read_only=True)
    total_raised = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'full_name', 'avatar', 'bio', 'region',
            'is_verified', 'campaign_count', 'total_raised', 'created_at',
        ]

    def get_avatar(self, obj):
        request = self.context.get('request')
        if obj.avatar and request:
            return request.build_absolute_uri(obj.avatar.url)
        return None

    def get_total_raised(self, obj):
        if not obj.show_total_raised:
            return None
        return obj.total_raised or 0


class IdentityVerificationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = IdentityVerification
        fields = ['id_type', 'id_number', 'id_photo_front', 'id_photo_back']

    def validate(self, data):
        if data.get('id_type') != IdentityVerification.IdType.PASSPORT and not data.get('id_photo_back'):
            raise serializers.ValidationError({'id_photo_back': 'Back photo is required for this ID type.'})
        return data


class IdentityVerificationSerializer(serializers.ModelSerializer):
    user_id = serializers.CharField(source='user.id', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()
    id_photo_front = serializers.SerializerMethodField()
    id_photo_back = serializers.SerializerMethodField()

    class Meta:
        model = IdentityVerification
        fields = [
            'id', 'user_id', 'user_name', 'user_email',
            'id_type', 'id_number', 'id_photo_front', 'id_photo_back',
            'status', 'rejection_reason', 'reviewed_by_name', 'reviewed_at', 'created_at',
        ]

    def get_reviewed_by_name(self, obj):
        return obj.reviewed_by.full_name if obj.reviewed_by else None

    def get_id_photo_front(self, obj):
        request = self.context.get('request')
        if obj.id_photo_front and request:
            return request.build_absolute_uri(obj.id_photo_front.url)
        return None

    def get_id_photo_back(self, obj):
        request = self.context.get('request')
        if obj.id_photo_back and request:
            return request.build_absolute_uri(obj.id_photo_back.url)
        return None


class OrganizationVerificationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationVerification
        fields = [
            'contact_id_type', 'contact_id_number', 'contact_id_photo_front', 'contact_id_photo_back',
            'registration_document', 'organization_photo',
        ]

    def validate(self, data):
        if data.get('contact_id_type') != OrganizationVerification.IdType.PASSPORT and not data.get('contact_id_photo_back'):
            raise serializers.ValidationError({'contact_id_photo_back': 'Back photo is required for this ID type.'})
        return data


class OrganizationVerificationSerializer(serializers.ModelSerializer):
    user_id = serializers.CharField(source='user.id', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    organization_type = serializers.CharField(source='user.organization.organization_type', read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()
    contact_id_photo_front = serializers.SerializerMethodField()
    contact_id_photo_back = serializers.SerializerMethodField()
    registration_document = serializers.SerializerMethodField()
    organization_photo = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationVerification
        fields = [
            'id', 'user_id', 'user_name', 'user_email', 'organization_type',
            'contact_id_type', 'contact_id_number', 'contact_id_photo_front', 'contact_id_photo_back',
            'registration_document', 'organization_photo',
            'status', 'rejection_reason', 'reviewed_by_name', 'reviewed_at', 'created_at',
        ]

    def get_reviewed_by_name(self, obj):
        return obj.reviewed_by.full_name if obj.reviewed_by else None

    def _absolute_url(self, field):
        request = self.context.get('request')
        if field and request:
            return request.build_absolute_uri(field.url)
        return None

    def get_contact_id_photo_front(self, obj):
        return self._absolute_url(obj.contact_id_photo_front)

    def get_contact_id_photo_back(self, obj):
        return self._absolute_url(obj.contact_id_photo_back)

    def get_registration_document(self, obj):
        return self._absolute_url(obj.registration_document)

    def get_organization_photo(self, obj):
        return self._absolute_url(obj.organization_photo)
