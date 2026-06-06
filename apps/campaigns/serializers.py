from rest_framework import serializers
from .models import Campaign, Category, CampaignImage, CampaignUpdate


class CategorySerializer(serializers.ModelSerializer):
    campaign_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'icon', 'campaign_count']

    def get_campaign_count(self, obj):
        return obj.campaigns.filter(status=Campaign.Status.ACTIVE).count()


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


class CampaignUpdateSerializer(serializers.ModelSerializer):
    posted_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CampaignUpdate
        fields = ['id', 'title', 'content', 'posted_by_name', 'created_at']

    def get_posted_by_name(self, obj):
        if obj.posted_by:
            return obj.posted_by.full_name
        return 'Campaign Owner'


class CampaignListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_slug = serializers.CharField(source='category.slug', read_only=True)
    owner_name = serializers.SerializerMethodField()
    progress_percent = serializers.ReadOnlyField()
    cover_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            'id', 'title', 'slug', 'short_description', 'cover_image_url',
            'goal', 'raised', 'currency', 'donors_count', 'progress_percent',
            'deadline', 'status', 'region', 'is_urgent', 'is_featured',
            'category_name', 'category_slug', 'owner_name', 'created_at',
        ]

    def get_owner_name(self, obj):
        if obj.is_anonymous:
            return 'Anonymous'
        return obj.owner.full_name

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
            'category', 'images', 'updates', 'owner_name',
            'total_withdrawn', 'available_balance',
            'approved_at', 'created_at', 'updated_at',
        ]

    def get_owner_name(self, obj):
        if obj.is_anonymous:
            return 'Anonymous'
        return obj.owner.full_name

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
    owner_email = serializers.CharField(source='owner.email', read_only=True)
    owner_name = serializers.CharField(source='owner.full_name', read_only=True)
    progress_percent = serializers.ReadOnlyField()

    class Meta:
        model = Campaign
        fields = [
            'id', 'title', 'slug', 'status', 'goal', 'raised', 'donors_count',
            'progress_percent', 'region', 'is_urgent', 'is_featured',
            'category_name', 'owner_email', 'owner_name',
            'rejection_reason', 'approved_at', 'created_at',
        ]
