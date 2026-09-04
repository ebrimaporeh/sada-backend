from django.db import models
from apps.core.models import BaseModel
from apps.users.models import User


class AuditLog(BaseModel):
    """One row per meaningful, state-changing business/security action --
    written by explicit calls to services/audit_service.py::log() at the
    specific point an action actually succeeds, not by generic HTTP-request
    capture.

    Deliberately NOT a blanket "every POST/PATCH" log (an earlier version of
    this was exactly that, and it drowned real actions in validation
    failures that changed nothing and product-engagement pings). The
    dividing line: "what did a user or the platform actually do?" -- a
    campaign page view or a share-button click is product engagement, not
    an audit event, and belongs in apps.events instead.
    """
    class Action(models.TextChoices):
        # Auth & account
        USER_LOGGED_IN = 'user.logged_in', 'Logged In'
        USER_REGISTERED = 'user.registered', 'Registered'
        USER_PASSWORD_RESET = 'user.password_reset', 'Reset Password'
        USER_PROFILE_UPDATED = 'user.profile_updated', 'Updated Profile'
        USER_ROLE_CHANGED = 'user.role_changed', "Changed User's Role"
        USER_ACCOUNT_DELETED = 'user.account_deleted', 'Deleted Account'
        STAFF_CREATED = 'staff.created', 'Created Staff Account'
        # Campaigns
        CAMPAIGN_CREATED = 'campaign.created', 'Created Campaign'
        CAMPAIGN_UPDATED = 'campaign.updated', 'Updated Campaign'
        CAMPAIGN_DELETED = 'campaign.deleted', 'Deleted Campaign'
        CAMPAIGN_PUBLISHED = 'campaign.published', 'Published Campaign'
        CAMPAIGN_UNPUBLISHED = 'campaign.unpublished', 'Unpublished Campaign'
        CAMPAIGN_REJECTED = 'campaign.rejected', 'Rejected Campaign'
        CAMPAIGN_COMPLETED = 'campaign.completed', 'Completed Campaign'
        CAMPAIGN_EXPIRED = 'campaign.expired', 'Expired Campaign'
        # Moderation
        REPORT_STATUS_CHANGED = 'report.status_changed', 'Updated Report'
        VERIFICATION_APPROVED = 'verification.approved', 'Approved Verification'
        VERIFICATION_REJECTED = 'verification.rejected', 'Rejected Verification'
        # Money
        DONATION_CREATED = 'donation.created', 'Created Donation'
        DONATION_STATUS_CHANGED = 'donation.status_changed', 'Donation Status Changed'
        PAYMENT_REFUNDED = 'payment.refunded', 'Refunded Payment'
        PAYOUT_REQUESTED = 'payout.requested', 'Requested Payout'
        PAYOUT_STATUS_CHANGED = 'payout.status_changed', 'Payout Status Changed'
        # Organizations
        ORGANIZATION_CREATED = 'organization.created', 'Created Organization'
        ORGANIZATION_OWNERSHIP_TRANSFERRED = 'organization.ownership_transferred', 'Transferred Ownership'
        ORGANIZATION_MEMBER_REMOVED = 'organization.member_removed', 'Removed Member'
        ORGANIZATION_MEMBER_ROLE_CHANGED = 'organization.member_role_changed', "Changed Member's Role"

    # The short verb shown as this action's badge in the activity list --
    # e.g. "created"/"updated"/"deleted" -- separate from the full sentence
    # in `description`, which repeats the actor's name and names the target
    # ("Alagie Admin created campaign \"...\"").
    VERBS = {
        Action.USER_LOGGED_IN: 'logged in',
        Action.USER_REGISTERED: 'registered',
        Action.USER_PASSWORD_RESET: 'reset password',
        Action.USER_PROFILE_UPDATED: 'updated',
        Action.USER_ROLE_CHANGED: 'updated',
        Action.USER_ACCOUNT_DELETED: 'deleted',
        Action.STAFF_CREATED: 'created',
        Action.CAMPAIGN_CREATED: 'created',
        Action.CAMPAIGN_UPDATED: 'updated',
        Action.CAMPAIGN_DELETED: 'deleted',
        Action.CAMPAIGN_PUBLISHED: 'published',
        Action.CAMPAIGN_UNPUBLISHED: 'unpublished',
        Action.CAMPAIGN_REJECTED: 'rejected',
        Action.CAMPAIGN_COMPLETED: 'completed',
        Action.CAMPAIGN_EXPIRED: 'expired',
        Action.REPORT_STATUS_CHANGED: 'updated',
        Action.VERIFICATION_APPROVED: 'approved',
        Action.VERIFICATION_REJECTED: 'rejected',
        Action.DONATION_CREATED: 'created',
        Action.DONATION_STATUS_CHANGED: 'updated',
        Action.PAYMENT_REFUNDED: 'refunded',
        Action.PAYOUT_REQUESTED: 'requested',
        Action.PAYOUT_STATUS_CHANGED: 'updated',
        Action.ORGANIZATION_CREATED: 'created',
        Action.ORGANIZATION_OWNERSHIP_TRANSFERRED: 'updated',
        Action.ORGANIZATION_MEMBER_REMOVED: 'removed',
        Action.ORGANIZATION_MEMBER_ROLE_CHANGED: 'updated',
    }

    # SET_NULL + denormalized name/email: self-service account deletion
    # anonymizes the User row (services/user_service.py::delete_own_account),
    # so a historical log entry needs its own copy of who acted to still
    # mean anything afterward. actor_name is what the UI actually displays
    # ("Alagie Admin"), never actor_email.
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    actor_name = models.CharField(max_length=255, blank=True)
    actor_email = models.CharField(max_length=255, blank=True)

    action = models.CharField(max_length=40, choices=Action.choices)

    # What the action was done to -- generic on purpose (a Campaign here,
    # a User there, a Donation elsewhere) rather than a FK per model, since
    # this table's whole point is being one place that covers all of them.
    target_type = models.CharField(max_length=50, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    target_repr = models.CharField(max_length=255, blank=True)

    description = models.CharField(max_length=500)
    metadata = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['actor']),
            models.Index(fields=['action']),
        ]

    @property
    def verb(self):
        return self.VERBS.get(self.action, 'updated')

    def __str__(self):
        return f'{self.get_action_display()} — {self.actor_name or self.actor_email or "System"}'
