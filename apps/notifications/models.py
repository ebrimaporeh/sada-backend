from django.db import models
from django.conf import settings
from apps.core.models import BaseModel


class Notification(BaseModel):
    class Type(models.TextChoices):
        DONATION_RECEIVED = 'donation_received', 'Donation Received'
        CAMPAIGN_APPROVED = 'campaign_approved', 'Campaign Approved'
        CAMPAIGN_REJECTED = 'campaign_rejected', 'Campaign Rejected'
        PAYOUT_PROCESSED = 'payout_processed', 'Payout Processed'
        CAMPAIGN_UPDATE = 'campaign_update', 'Campaign Update'
        GOAL_REACHED = 'goal_reached', 'Goal Reached'
        DONATION_REFUNDED = 'donation_refunded', 'Donation Refunded'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notification_type = models.CharField(max_length=30, choices=Type.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email}: {self.title}'
