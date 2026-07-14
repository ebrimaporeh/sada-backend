from rest_framework import serializers
from .models import Donation

# ModemPay rejects a single payment intent above this amount ("Amount for
# payment intent cannot exceed GMD 50,000.00") — validate here so it fails
# cleanly at submission instead of after a wasted DB write + API round-trip.
MAX_DONATION_AMOUNT = 50000


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
    phone = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Donation
        fields = ['campaign_id', 'amount', 'provider', 'phone', 'is_anonymous', 'message', 'donor_name']

    def validate_amount(self, value):
        if value < 5:
            raise serializers.ValidationError('Minimum donation is D5.')
        if value > MAX_DONATION_AMOUNT:
            raise serializers.ValidationError(
                f'Maximum donation amount is D{MAX_DONATION_AMOUNT:,} per transaction. '
                f'For larger amounts, please split into multiple donations.'
            )
        return value

    def validate_phone(self, value):
        if not value:
            return value
        digits = value.replace('+', '').replace(' ', '')
        if not digits.isdigit():
            raise serializers.ValidationError('Invalid phone number.')
        return value

    def validate(self, data):
        from apps.payments.models import PlatformSettings

        if data.get('provider') == Donation.Provider.CARD:
            if not PlatformSettings.get_solo().card_payments_enabled:
                raise serializers.ValidationError({'provider': 'Card payments are not currently available.'})
        elif not data.get('phone'):
            raise serializers.ValidationError({'phone': 'Phone number is required for this payment method.'})
        return data


class AdminDonationSerializer(serializers.ModelSerializer):
    donor_name = serializers.SerializerMethodField()
    donor_email = serializers.SerializerMethodField()
    campaign_title = serializers.CharField(source='campaign.title', read_only=True)
    net_amount = serializers.ReadOnlyField()

    class Meta:
        model = Donation
        fields = [
            'id', 'amount', 'currency', 'provider', 'phone', 'status',
            'is_anonymous', 'message', 'fee', 'net_amount',
            'donor_name', 'donor_email', 'campaign_title', 'payment_reference',
            'provider_reference', 'paid_at', 'created_at',
        ]

    def get_donor_name(self, obj):
        return obj.donor_display

    def get_donor_email(self, obj):
        if obj.donor:
            return obj.donor.email
        return 'Anonymous'


class AdminDonationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Donation
        fields = [
            'amount', 'status', 'phone', 'provider',
            'is_anonymous', 'message', 'fee',
        ]

    def validate_amount(self, value):
        if value < 5:
            raise serializers.ValidationError('Minimum donation is D5.')
        return value

    def validate_phone(self, value):
        digits = value.replace('+', '').replace(' ', '')
        if not digits.isdigit():
            raise serializers.ValidationError('Invalid phone number.')
        return value
