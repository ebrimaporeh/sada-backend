from decimal import Decimal
from rest_framework import serializers
from .models import Payment, Payout, PlatformSettings


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'provider', 'amount', 'currency', 'reference', 'status', 'completed_at', 'created_at']


class PayoutCreateSerializer(serializers.ModelSerializer):
    campaign_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Payout
        fields = ['campaign_id', 'amount', 'provider', 'phone']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('Amount must be positive.')
        return value

    def validate_provider(self, value):
        # Payouts are modempay-only (Stripe/card donations have no payout
        # path to a Gambian mobile-money wallet) — Payout.Provider has more
        # choices for historical reasons (shared with Donation/Payment), but
        # only modempay's supported networks can actually be paid out.
        from services.gateways.registry import get_gateway
        supported = get_gateway('modempay').supported_payout_methods
        if value not in supported:
            raise serializers.ValidationError(
                f'Withdrawals are only supported via {" or ".join(sorted(supported))} at this time.'
            )
        return value


class PayoutFeePreviewSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0.01'))
    provider = serializers.CharField()

    def validate_provider(self, value):
        from services.gateways.registry import get_gateway
        supported = get_gateway('modempay').supported_payout_methods
        if value not in supported:
            raise serializers.ValidationError(
                f'Withdrawals are only supported via {" or ".join(sorted(supported))} at this time.'
            )
        return value


class PayoutSerializer(serializers.ModelSerializer):
    campaign_title = serializers.CharField(source='campaign.title', read_only=True)

    class Meta:
        model = Payout
        fields = [
            'id', 'campaign_title', 'amount', 'fee', 'provider_fee', 'net_amount', 'currency',
            'provider', 'phone', 'reference', 'status', 'notes',
            'processed_at', 'created_at',
        ]


class PlatformSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformSettings
        fields = [
            'platform_fee_percent', 'modempay_enabled', 'stripe_enabled',
            'stripe_settlement_currency', 'gmd_to_settlement_rate',
        ]

    def validate_platform_fee_percent(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError('Platform fee must be between 0 and 100.')
        return value

    def validate_gmd_to_settlement_rate(self, value):
        if value <= 0:
            raise serializers.ValidationError('Exchange rate must be positive.')
        return value

    def validate_stripe_enabled(self, value):
        from django.conf import settings
        if value and not settings.PAYMENT_GATEWAYS.get('stripe', {}).get('secret_key'):
            raise serializers.ValidationError(
                'Cannot enable Stripe — STRIPE_SECRET_KEY is not configured on this server.'
            )
        return value
