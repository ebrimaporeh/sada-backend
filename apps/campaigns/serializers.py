from rest_framework import serializers
from .models import Campaign, Category, CampaignImage, CampaignUpdate, CampaignUpdateImage, CampaignReport


class CategorySerializer(serializers.ModelSerializer):
    campaign_count = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    total_donated = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'icon', 'image_url', 'campaign_count', 'total_donated']

    def get_campaign_count(self, obj):
        return obj.campaigns.filter(status=Campaign.Status.ACTIVE).count()

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None

    def get_total_donated(self, obj):
        # get_categories() annotates this for the ordered list endpoint;
        # fall back to computing it directly for detail views that fetch
        # the Category without going through that annotation.
        if hasattr(obj, 'total_donated'):
            return obj.total_donated or 0
        from django.db.models import Sum
        from apps.donations.models import Donation
        total = obj.campaigns.filter(donations__status=Donation.Status.PAID).aggregate(
            t=Sum('donations__amount')
        )['t']
        return total or 0


class CampaignImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = CampaignImage
        fields = ['id', 'image_url', 'order', 'is_cover']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class CampaignUpdateImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = CampaignUpdateImage
        fields = ['id', 'image_url', 'order']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class CampaignUpdateSerializer(serializers.ModelSerializer):
    posted_by_name = serializers.SerializerMethodField()
    images = CampaignUpdateImageSerializer(many=True, read_only=True)

    class Meta:
        model = CampaignUpdate
        fields = ['id', 'title', 'content', 'posted_by_name', 'images', 'created_at']

    def get_posted_by_name(self, obj):
        if obj.posted_by:
            return obj.posted_by.full_name
        return 'Campaign Owner'


class CampaignListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    owner_name = serializers.SerializerMethodField()
    owner_is_verified = serializers.SerializerMethodField()
    progress_percent = serializers.ReadOnlyField()
    cover_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            'id', 'title', 'slug', 'short_description', 'cover_image_url',
            'goal', 'raised', 'currency', 'donors_count', 'progress_percent',
            'deadline', 'status', 'region', 'is_urgent', 'is_featured',
            'category_name', 'category_slug', 'owner_name', 'owner_is_verified', 'created_at',
        ]

    def get_owner_name(self, obj):
        if obj.is_anonymous:
            return 'Anonymous'
        return obj.owner.full_name

    def get_owner_is_verified(self, obj):
        if obj.is_anonymous:
            return False
        return obj.owner.is_verified

    def get_cover_image_url(self, obj):
        request = self.context.get('request')
        if obj.cover_image and request:
            return request.build_absolute_uri(obj.cover_image.url)
        return None


class CampaignDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    images = CampaignImageSerializer(many=True, read_only=True)
    updates = CampaignUpdateSerializer(many=True, read_only=True)
    owner_name = serializers.SerializerMethodField()
    owner_is_verified = serializers.SerializerMethodField()
    progress_percent = serializers.ReadOnlyField()
    cover_image_url = serializers.SerializerMethodField()
    total_withdrawn = serializers.SerializerMethodField()
    available_balance = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            'id', 'title', 'slug', 'short_description', 'story', 'cover_image_url',
            'goal', 'raised', 'currency', 'donors_count', 'views_count',
            'progress_percent', 'deadline', 'status', 'region',
            'beneficiary', 'beneficiary_relationship',
            'is_urgent', 'is_featured', 'is_anonymous',
            'category', 'images', 'updates', 'owner_name', 'owner_is_verified',
            'total_withdrawn', 'available_balance',
            'approved_at', 'created_at', 'updated_at',
        ]

    def get_owner_name(self, obj):
        if obj.is_anonymous:
            return 'Anonymous'
        return obj.owner.full_name

    def get_owner_is_verified(self, obj):
        if obj.is_anonymous:
            return False
        return obj.owner.is_verified

    def get_cover_image_url(self, obj):
        request = self.context.get('request')
        if obj.cover_image and request:
            return request.build_absolute_uri(obj.cover_image.url)
        return None

    def get_total_withdrawn(self, obj):
        from apps.payments.models import Payout
        from django.db.models import Sum
        active = [Payout.Status.PENDING, Payout.Status.PROCESSING, Payout.Status.COMPLETED]
        total = obj.payouts.filter(status__in=active).aggregate(t=Sum('amount'))['t']
        return total or 0

    def get_available_balance(self, obj):
        from apps.payments.models import Payout
        from django.db.models import Sum
        from decimal import Decimal
        active = [Payout.Status.PENDING, Payout.Status.PROCESSING, Payout.Status.COMPLETED]
        withdrawn = obj.payouts.filter(status__in=active).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        return max(obj.raised - withdrawn, Decimal('0'))


class CampaignCreateSerializer(serializers.ModelSerializer):
    category_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    category = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Category.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Campaign
        fields = [
            'title', 'short_description', 'story', 'goal', 'deadline',
            'region', 'beneficiary', 'beneficiary_relationship',
            'is_urgent', 'is_anonymous', 'category_id', 'category',
        ]

    def validate(self, data):
        # Accept category slug and convert to category_id for the service layer
        category_obj = data.pop('category', None)
        if category_obj is not None:
            data['category_id'] = category_obj.id
        return data

    def validate_goal(self, value):
        if value <= 0:
            raise serializers.ValidationError('Goal must be greater than zero.')
        return value


class CampaignUpdateCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignUpdate
        fields = ['title', 'content']


class AdminCampaignSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    owner_id = serializers.CharField(source='owner.id', read_only=True)
    owner_email = serializers.CharField(source='owner.email', read_only=True)
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    owner_phone = serializers.CharField(source='owner.phone', read_only=True)
    owner_joined_at = serializers.DateTimeField(source='owner.created_at', read_only=True)
    progress_percent = serializers.ReadOnlyField()
    cover_image_url = serializers.SerializerMethodField()
    images = CampaignImageSerializer(many=True, read_only=True)
    updates = CampaignUpdateSerializer(many=True, read_only=True)
    updates_count = serializers.SerializerMethodField()
    reports_count = serializers.SerializerMethodField()
    pending_reports_count = serializers.SerializerMethodField()
    total_withdrawn = serializers.SerializerMethodField()
    available_balance = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            'id', 'title', 'slug', 'status', 'goal', 'raised', 'currency', 'donors_count',
            'views_count', 'progress_percent', 'region', 'is_urgent', 'is_featured', 'is_anonymous',
            'cover_image_url', 'images', 'updates', 'updates_count',
            'category_name', 'category_slug',
            'owner_id', 'owner_email', 'owner_name', 'owner_phone', 'owner_joined_at',
            'story', 'beneficiary', 'beneficiary_relationship', 'deadline',
            'short_description', 'rejection_reason',
            'total_withdrawn', 'available_balance',
            'reports_count', 'pending_reports_count',
            'approved_at', 'completed_at', 'created_at', 'updated_at',
        ]

    def get_cover_image_url(self, obj):
        request = self.context.get('request')
        if obj.cover_image and request:
            return request.build_absolute_uri(obj.cover_image.url)
        return None

    def get_updates_count(self, obj):
        return obj.updates.count()

    def get_reports_count(self, obj):
        return obj.reports.count()

    def get_pending_reports_count(self, obj):
        return obj.reports.filter(status=CampaignReport.Status.PENDING).count()

    def get_total_withdrawn(self, obj):
        from apps.payments.models import Payout
        from django.db.models import Sum
        active = [Payout.Status.PENDING, Payout.Status.PROCESSING, Payout.Status.COMPLETED]
        total = obj.payouts.filter(status__in=active).aggregate(t=Sum('amount'))['t']
        return total or 0

    def get_available_balance(self, obj):
        from apps.payments.models import Payout
        from django.db.models import Sum
        from decimal import Decimal
        active = [Payout.Status.PENDING, Payout.Status.PROCESSING, Payout.Status.COMPLETED]
        withdrawn = obj.payouts.filter(status__in=active).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        return max(obj.raised - withdrawn, Decimal('0'))


class CampaignReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignReport
        fields = ['reason', 'description', 'reporter_name', 'reporter_phone']


class CampaignReportSerializer(serializers.ModelSerializer):
    reported_by_name = serializers.SerializerMethodField()
    reported_by_email = serializers.SerializerMethodField()
    campaign_id = serializers.SerializerMethodField()
    campaign = serializers.SerializerMethodField()

    class Meta:
        model = CampaignReport
        fields = [
            'id', 'campaign_id', 'campaign', 'reason', 'description', 'status',
            'reported_by_name', 'reported_by_email', 'reporter_phone', 'created_at', 'admin_notes',
        ]

    def get_reported_by_name(self, obj):
        if obj.reported_by:
            return obj.reported_by.full_name
        return obj.reporter_name or 'Anonymous'

    def get_reported_by_email(self, obj):
        if obj.reported_by:
            return obj.reported_by.email
        return None

    def get_campaign_id(self, obj):
        return str(obj.campaign.id) if obj.campaign else None

    def get_campaign(self, obj):
        if obj.campaign:
            return {
                'id': str(obj.campaign.id),
                'title': obj.campaign.title,
                'slug': obj.campaign.slug,
                'status': obj.campaign.status,
                'owner': {
                    'id': str(obj.campaign.owner.id),
                    'full_name': obj.campaign.owner.full_name,
                    'email': obj.campaign.owner.email,
                } if obj.campaign.owner else None,
                'raised': float(obj.campaign.raised or 0),
                'goal': float(obj.campaign.goal or 0),
            }
        return None


class AdminCampaignUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Campaign
        fields = [
            'title', 'short_description', 'story', 'goal', 'status',
            'region', 'beneficiary', 'beneficiary_relationship',
            'is_urgent', 'is_featured', 'rejection_reason', 'deadline',
        ]

    def validate_goal(self, value):
        if value <= 0:
            raise serializers.ValidationError('Goal must be greater than zero.')
        return value


class CampaignReportUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignReport
        fields = ['status', 'admin_notes', 'reason', 'description']
