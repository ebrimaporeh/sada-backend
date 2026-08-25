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
            'id', 'amount', 'currency', 'gateway', 'provider', 'phone', 'status',
            'is_anonymous', 'message', 'fee', 'net_amount',
            'donor_name', 'campaign_title', 'campaign_slug',
            'payment_reference', 'paid_at', 'created_at',
        ]

    def get_donor_name(self, obj):
        return obj.donor_display


class DonationCreateSerializer(serializers.ModelSerializer):
    campaign_id = serializers.UUIDField(write_only=True)
    # Not model-reflected on purpose: no choices= here, since gateways are
    # registered in services/gateways/registry.py, not a fixed enum.
    gateway = serializers.CharField(required=False, default='modempay')

    class Meta:
        model = Donation
        fields = ['campaign_id', 'amount', 'gateway', 'provider', 'phone', 'is_anonymous', 'message', 'donor_name']

    def validate_amount(self, value):
        # The real min/max are per-gateway and admin-configurable
        # (PlatformSettings.<code>_min/max_donation_amount) -- enforced in
        # validate() below, once the gateway is resolved. This is just a
        # basic sanity floor independent of which gateway ends up selected.
        if value <= 0:
            raise serializers.ValidationError('Donation amount must be greater than zero.')
        return value

    def validate_gateway(self, value):
        from services.gateways.registry import get_gateway
        get_gateway(value)  # raises ValidationError if unknown/disabled
        return value

    def validate_phone(self, value):
        if not value:
            return value
        digits = value.replace('+', '').replace(' ', '')
        if not digits.isdigit():
            raise serializers.ValidationError('Invalid phone number.')
        return value

    def validate(self, data):
        from services.gateways.registry import get_gateway, donation_amount_limits
        gateway_code = data.get('gateway') or 'modempay'
        gateway = get_gateway(gateway_code)

        amount = data.get('amount')
        if amount is not None:
            min_amount, max_amount = donation_amount_limits(gateway_code)
            if amount < min_amount:
                raise serializers.ValidationError({'amount': f'Minimum donation is D{min_amount:,.0f}.'})
            if amount > max_amount:
                raise serializers.ValidationError({
                    'amount': f'Maximum donation amount is D{max_amount:,.0f} per transaction. '
                              f'For larger amounts, please split into multiple donations.',
                })

        if gateway.default_method:
            data['provider'] = gateway.default_method
        else:
            provider = data.get('provider') or Donation.Provider.WAVE
            if provider not in gateway.supported_donation_methods:
                raise serializers.ValidationError({'provider': f'"{provider}" is not currently available.'})
            data['provider'] = provider
        if gateway.requires_phone and not data.get('phone'):
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
            'id', 'amount', 'currency', 'gateway', 'provider', 'phone', 'status',
            'is_anonymous', 'message', 'fee', 'net_amount',
            'donor_name', 'donor_email', 'campaign_title', 'payment_reference',
            'provider_reference', 'paid_at', 'refunded_at', 'refund_reason', 'created_at',
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
        if not value:
            return value
        digits = value.replace('+', '').replace(' ', '')
        if not digits.isdigit():
            raise serializers.ValidationError('Invalid phone number.')
        return value


class AdminDonationRefundSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='')
