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
        # ModemPay's mobile-money payout API only supports these two
        # networks — Payout.Provider has more choices for historical reasons
        # (shared with Donation/Payment), but only these can actually be paid out.
        from services.modempay_service import SUPPORTED_PAYOUT_NETWORKS
        if value not in SUPPORTED_PAYOUT_NETWORKS:
            raise serializers.ValidationError(
                f'Withdrawals are only supported via {" or ".join(sorted(SUPPORTED_PAYOUT_NETWORKS))} at this time.'
            )
        return value


class PayoutSerializer(serializers.ModelSerializer):
    campaign_title = serializers.CharField(source='campaign.title', read_only=True)

    class Meta:
        model = Payout
        fields = [
            'id', 'campaign_title', 'amount', 'fee', 'net_amount', 'currency',
            'provider', 'phone', 'reference', 'status', 'notes',
            'processed_at', 'created_at',
        ]


class PlatformSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformSettings
        fields = ['platform_fee_percent']

    def validate_platform_fee_percent(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError('Platform fee must be between 0 and 100.')
        return value
