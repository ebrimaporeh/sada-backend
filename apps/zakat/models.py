from decimal import Decimal
from django.db import models
from apps.core.models import BaseModel


class ZakatSettings(BaseModel):
    """Singleton row of admin-editable Zakat calculation config.

    Nisab (the minimum wealth threshold that makes Zakat obligatory) is
    classically defined as the value of a fixed weight of gold or silver,
    not a flat currency figure — metal prices move, so the GMD-equivalent
    threshold has to be computed from a weight + a price the admin keeps
    up to date, rather than hardcoded. Silver is the default basis: it's
    the lower of the two thresholds, and the majority of contemporary
    scholars favor it precisely because it brings more people into the
    obligation (and therefore more relief to recipients) than the much
    higher gold nisab would.
    """
    class NisabBasis(models.TextChoices):
        GOLD = 'gold', 'Gold'
        SILVER = 'silver', 'Silver'

    nisab_basis = models.CharField(max_length=10, choices=NisabBasis.choices, default=NisabBasis.SILVER)

    # Classical weights (87.48g gold / 612.36g silver) — editable per
    # settings-driven convention, but admins should only touch these if
    # acting on specific fiqh guidance, not to move the threshold casually.
    nisab_gold_grams = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('87.48'))
    nisab_silver_grams = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('612.36'))

    gold_price_per_gram = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    silver_price_per_gram = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))

    zakat_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('2.50'),
        help_text='Percentage of zakatable wealth owed once it reaches nisab. Classically fixed at 2.5%.',
    )

    # Optional flat override, in GMD, for an admin who'd rather set the
    # threshold directly than maintain metal prices — takes precedence
    # over the computed gold/silver nisab when set.
    minimum_amount_override = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        verbose_name = 'Zakat Settings'
        verbose_name_plural = 'Zakat Settings'

    def __str__(self):
        return f'Zakat: {self.zakat_percentage}% above {self.nisab_amount} GMD nisab'

    @classmethod
    def get_solo(cls):
        obj = cls.objects.first()
        if obj is None:
            obj = cls.objects.create()
        return obj

    @property
    def nisab_amount(self) -> Decimal:
        if self.minimum_amount_override is not None:
            return self.minimum_amount_override
        if self.nisab_basis == self.NisabBasis.GOLD:
            return self.nisab_gold_grams * self.gold_price_per_gram
        return self.nisab_silver_grams * self.silver_price_per_gram
