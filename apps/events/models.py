from django.db import models
from apps.core.models import BaseModel
from apps.users.models import User


class Event(BaseModel):
    """Product-engagement tracking -- "what are users doing," not "what
    important thing happened to the system." Separate from apps.audit on
    purpose: a campaign page view or a share-button click isn't an
    administrative action worth an admin poring over, and mixing the two
    drowns the audit log in noise (that's exactly what
    POST /campaigns/<slug>/view/ was doing before this existed).
    """
    class Type(models.TextChoices):
        CAMPAIGN_VIEWED = 'campaign_viewed', 'Campaign Viewed'
        CAMPAIGN_SHARED = 'campaign_shared', 'Campaign Shared'
        CAMPAIGN_CLICKED = 'campaign_clicked', 'Campaign Clicked'
        DONATION_STARTED = 'donation_started', 'Donation Started'
        DONATION_AMOUNT_SELECTED = 'donation_amount_selected', 'Donation Amount Selected'
        DONATION_COMPLETED = 'donation_completed', 'Donation Completed'

    type = models.CharField(max_length=40, choices=Type.choices)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='events')
    # Client-generated, carried across an anonymous visitor's requests so
    # e.g. donation_started -> donation_completed for the same guest can be
    # correlated without needing an account. Not a security boundary --
    # purely a funnel-analysis convenience.
    session_id = models.CharField(max_length=64, blank=True)
    campaign = models.ForeignKey('campaigns.Campaign', on_delete=models.SET_NULL, null=True, blank=True, related_name='events')
    metadata = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['type']),
            models.Index(fields=['campaign']),
            models.Index(fields=['session_id']),
        ]

    def __str__(self):
        return f'{self.get_type_display()} ({self.created_at:%Y-%m-%d %H:%M})'
