from rest_framework import serializers
from .models import Donation


class DonationSerializer(serializers.ModelSerializer):
    donor_name = serializers.SerializerMethodField()
    campaign_title = serializers.CharField(source='campaign.title', read_only=True)
    campaign_slug = serializers.CharField(source='campaign.slug', read_only=True)
    net_amount = serializers.ReadOnlyField()

    class Meta:
        model = Donation
        fields = [
            'id', 'amount', 'currency', 'provider', 'phone', 'status',
            'is_anonymous', 'message', 'fee', 'net_amount',
            'donor_name', 'campaign_title', 'campaign_slug',
            'payment_reference', 'paid_at', 'created_at',
        ]

    def get_donor_name(self, obj):
        return obj.donor_display


class DonationCreateSerializer(serializers.ModelSerializer):
    campaign_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Donation
        fields = ['campaign_id', 'amount', 'provider', 'phone', 'is_anonymous', 'message']

    def validate_amount(self, value):
        if value < 5:
            raise serializers.ValidationError('Minimum donation is D5.')
        return value

    def validate_phone(self, value):
        digits = value.replace('+', '').replace(' ', '')
        if not digits.isdigit():
            raise serializers.ValidationError('Invalid phone number.')
        return value


class AdminDonationSerializer(serializers.ModelSerializer):
    donor_email = serializers.SerializerMethodField()
    campaign_title = serializers.CharField(source='campaign.title', read_only=True)
    net_amount = serializers.ReadOnlyField()

    class Meta:
        model = Donation
        fields = [
            'id', 'amount', 'currency', 'provider', 'phone', 'status',
            'is_anonymous', 'message', 'fee', 'net_amount',
            'donor_email', 'campaign_title', 'payment_reference',
            'provider_reference', 'paid_at', 'created_at',
        ]

    def get_donor_email(self, obj):
        if obj.donor:
            return obj.donor.email
        return 'Anonymous'
