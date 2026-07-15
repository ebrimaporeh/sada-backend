from decimal import Decimal


def get_settings():
    from apps.zakat.models import ZakatSettings
    return ZakatSettings.get_solo()


def calculate_zakat(inputs: dict) -> dict:
    """`inputs` is validated ZakatCalculationInputSerializer data. Sums
    zakatable assets, deducts debts, and compares the result to nisab —
    the classical "if your wealth has sat above this threshold for a
    lunar year, 2.5% of it is due" rule. Debts are deducted before the
    nisab comparison since only wealth actually available to you counts."""
    settings_obj = get_settings()

    assets = (
        inputs['cash_and_savings']
        + inputs['gold_and_silver_value']
        + inputs['business_assets']
        + inputs['investments']
        + inputs['money_owed_to_you']
    )
    zakatable_wealth = max(assets - inputs['debts_you_owe'], Decimal('0'))

    nisab_amount = settings_obj.nisab_amount
    is_eligible = nisab_amount > 0 and zakatable_wealth >= nisab_amount
    zakat_due = (zakatable_wealth * settings_obj.zakat_percentage / Decimal('100')) if is_eligible else Decimal('0')

    return {
        'zakatable_wealth': zakatable_wealth,
        'nisab_amount': nisab_amount,
        'zakat_percentage': settings_obj.zakat_percentage,
        'is_eligible': is_eligible,
        'zakat_due': zakat_due.quantize(Decimal('0.01')),
    }
