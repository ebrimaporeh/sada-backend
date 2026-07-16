from decimal import Decimal
from rest_framework import serializers
from .models import ZakatSettings


class ZakatSettingsSerializer(serializers.ModelSerializer):
    nisab_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = ZakatSettings
        fields = [
            'nisab_gold_grams', 'nisab_silver_grams',
            'gold_price_per_gram', 'silver_price_per_gram',
            'zakat_percentage', 'minimum_amount_override', 'nisab_amount',
        ]

    def validate_zakat_percentage(self, value):
        if value <= 0 or value > 100:
            raise serializers.ValidationError('Zakat percentage must be between 0 and 100.')
        return value

    def validate_minimum_amount_override(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Minimum amount cannot be negative.')
        return value


class ZakatCalculationInputSerializer(serializers.Serializer):
    """Assets/liabilities a donor enters — mirrors the classical zakatable
    wealth categories: cash and savings, gold/silver holdings, business
    trade goods, investments, money owed to them (receivables), minus
    debts they owe (liabilities are deducted before comparing to nisab)."""
    cash_and_savings = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'), min_value=Decimal('0'))
    gold_and_silver_value = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'), min_value=Decimal('0'))
    business_assets = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'), min_value=Decimal('0'))
    investments = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'), min_value=Decimal('0'))
    money_owed_to_you = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'), min_value=Decimal('0'))
    debts_you_owe = serializers.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'), min_value=Decimal('0'))
