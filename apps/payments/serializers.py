from rest_framework import serializers
from .models import Payment, Payout


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


class PayoutSerializer(serializers.ModelSerializer):
    campaign_title = serializers.CharField(source='campaign.title', read_only=True)

    class Meta:
        model = Payout
        fields = [
            'id', 'campaign_title', 'amount', 'fee', 'net_amount', 'currency',
            'provider', 'phone', 'reference', 'status', 'notes',
            'processed_at', 'created_at',
        ]
