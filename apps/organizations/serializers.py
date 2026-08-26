from rest_framework import serializers
from apps.users.models import Organization
from .models import OrganizationType, OrganizationRole, OrganizationMembership, OrganizationInvitation
import services.organization_service as organization_service


class OrganizationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationType
        fields = ['slug', 'name', 'description']


class OrganizationRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrganizationRole
        fields = ['id', 'name', 'permissions', 'created_at']


class OrganizationRoleCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50)
    permissions = serializers.ListField(child=serializers.CharField(), required=False, default=list)


class OrganizationRoleUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=50, required=False)
    permissions = serializers.ListField(child=serializers.CharField(), required=False)


class OrganizationSerializer(serializers.ModelSerializer):
    """Detail shape for a single organization -- distinct from the lean
    per-membership shape UserSerializer.get_organizations returns (that one
    also carries the requesting user's own role/permissions inline)."""
    organization_type = serializers.CharField(source='organization_type.slug', read_only=True)
    organization_type_name = serializers.CharField(source='organization_type.name', read_only=True)
    logo = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    # Replaces the old free-text contact_person_name -- real members
    # flagged via OrganizationMembership.is_contact_person, each with their
    # own actual name/email/phone (from their User record), not a name that
    # can drift from who's actually reachable.
    contact_persons = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            'id', 'organization_name', 'organization_type', 'organization_type_name',
            'phone', 'phone_2', 'recovery_email_1', 'recovery_email_2', 'logo',
            'is_verified', 'member_count', 'created_by_name', 'contact_persons', 'created_at',
        ]

    def get_logo(self, obj):
        request = self.context.get('request')
        if obj.logo and request:
            return request.build_absolute_uri(obj.logo.url)
        return None

    def get_member_count(self, obj):
        return obj.memberships.count()

    def get_created_by_name(self, obj):
        return obj.created_by.full_name if obj.created_by else None

    def get_contact_persons(self, obj):
        return [
            {'user_id': str(m.user_id), 'name': m.user.full_name, 'email': m.user.email, 'phone': m.user.phone}
            for m in obj.memberships.filter(is_contact_person=True).select_related('user')
        ]


class AdminOrganizationListSerializer(serializers.ModelSerializer):
    """Lean projection for the admin Fundraisers page's Organizations tab --
    mirrors AdminUserListSerializer/AdminCampaignListSerializer's reasoning
    (list-only, not the full detail shape a single-org admin page needs)."""
    organization_type_name = serializers.CharField(source='organization_type.name', read_only=True)
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = ['id', 'organization_name', 'organization_type_name', 'member_count', 'is_verified', 'created_at']

    def get_member_count(self, obj):
        return obj.memberships.count()


class OrganizationCreateSerializer(serializers.Serializer):
    """Field names here are passed straight through to
    organization_service.create_organization(**validated_data) --
    organization_type_slug (not organization_type/organization_type_id)
    because OrganizationType is looked up by its slug, not its id."""
    organization_name = serializers.CharField(max_length=200)
    organization_type_slug = serializers.SlugField()
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    phone_2 = serializers.CharField(max_length=20, required=False, allow_blank=True)
    recovery_email_1 = serializers.EmailField(required=False, allow_blank=True)
    recovery_email_2 = serializers.EmailField(required=False, allow_blank=True)


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.CharField(source='user.id', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    role_id = serializers.CharField(source='role.id', read_only=True)
    role_name = serializers.CharField(source='role.name', read_only=True)
    permissions = serializers.ListField(source='role.permissions', read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = [
            'id', 'user_id', 'user_name', 'user_email', 'user_phone', 'role_id', 'role_name',
            'permissions', 'is_contact_person', 'created_at',
        ]


class UpdateMemberSerializer(serializers.Serializer):
    """Both fields optional and independent -- a PATCH can change the
    member's role, their contact-person flag, or both in one call. See
    OrganizationMemberDetailView.patch."""
    role_id = serializers.UUIDField(required=False)
    is_contact_person = serializers.BooleanField(required=False)

    def validate(self, data):
        if not data:
            raise serializers.ValidationError('Provide role_id and/or is_contact_person.')
        return data


class OrganizationInvitationSerializer(serializers.ModelSerializer):
    organization_id = serializers.CharField(source='organization.id', read_only=True)
    organization_name = serializers.CharField(source='organization.organization_name', read_only=True)
    role_id = serializers.CharField(source='role.id', read_only=True)
    role_name = serializers.CharField(source='role.name', read_only=True)
    invited_by_name = serializers.SerializerMethodField()
    # Lets the "my invitations" dashboard list link straight to the accept/
    # reject page without the user having to go back to the email. Also
    # visible on the org-facing pending-invitations list (this serializer is
    # shared), but that's harmless: accept_invitation/reject_invitation both
    # hard-require invitation.email == the acting user's own email, so an
    # org manager holding this token still can't act as the invitee with it.
    token = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationInvitation
        fields = [
            'id', 'organization_id', 'organization_name', 'email', 'role_id', 'role_name',
            'invited_by_name', 'status', 'token', 'created_at', 'responded_at',
        ]

    def get_invited_by_name(self, obj):
        return obj.invited_by.full_name if obj.invited_by else None

    def get_token(self, obj):
        if obj.status != OrganizationInvitation.Status.PENDING:
            return None
        return organization_service.generate_invitation_token(obj)


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role_id = serializers.UUIDField()
