"""Fundraising Studio -- Poster Studio and Embed Studio.

Two independently-managed distribution/presentation tools that both point
at the platform's two existing donation destinations (Organization or
Campaign, see FundraisingDestination in services/fundraising_destination.py)
rather than introducing a new fundraising/destination concept of their own.
Poster and Embed are deliberately separate model classes (not a shared
generic "Studio item" base) -- see .claude/backend/fundraising.md for the
full architecture writeup. The destination_type/campaign/organization field
trio and its CheckConstraint are duplicated across the two models rather
than factored into a shared base or mixin -- small, explicit duplication
over cleverness, same call this codebase already makes for per-model enums
(see .claude/backend/models.md). Both mirror
apps.donations.models.Donation's existing "exactly one destination"
pattern, so this doesn't invent a second way to express the same idea.
"""
from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from utils.upload_paths import poster_image_path


class DestinationType(models.TextChoices):
    """Shared by Poster and Embed -- both live in this one app and both feed
    the same services/fundraising_destination.py::resolve_destination(),
    so keeping one enum here (instead of duplicating it per-model) avoids
    the two ever disagreeing on what values that function accepts."""
    ORGANIZATION = 'organization', 'Organization'
    CAMPAIGN = 'campaign', 'Campaign'


class Poster(BaseModel):
    class Template(models.TextChoices):
        CLASSIC = 'classic', 'Classic'
        MODERN = 'modern', 'Modern'
        MINIMAL = 'minimal', 'Minimal'
        BOLD = 'bold', 'Bold'
        COMMUNITY = 'community', 'Community'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'

    destination_type = models.CharField(max_length=20, choices=DestinationType.choices)
    # Campaign hard-delete is real but restricted to DRAFT/REJECTED
    # campaigns only (see campaign_service.delete_campaign) -- i.e.
    # campaigns that were never public and never raised money, so never
    # legitimately had a poster printed or an embed installed against them.
    # CASCADE here mirrors Donation.campaign's existing CASCADE choice and
    # is safe specifically because of that status restriction, not a
    # blanket assumption.
    campaign = models.ForeignKey(
        'campaigns.Campaign', on_delete=models.CASCADE, null=True, blank=True, related_name='posters',
    )
    # Organization has NO hard-delete code path anywhere in this codebase
    # today (checked services/user_service.py, organization views/services,
    # admin, management commands -- even self-service account deletion
    # explicitly leaves the organization itself untouched, see
    # delete_own_account's docstring). PROTECT is a deliberate, defensive
    # choice for something that may already be printed and physically
    # distributed: if an organization-delete feature is ever added, it must
    # not silently cascade away a poster (and the now-dead QR code on
    # printed material) without whoever builds that feature consciously
    # deciding what happens to it first.
    organization = models.ForeignKey(
        'users.Organization', on_delete=models.PROTECT, null=True, blank=True, related_name='posters',
    )
    # Denormalized, audit/display only -- same convention as
    # Organization.created_by. Never used for access control (ownership is
    # resolved via campaign/organization, exactly like the models
    # themselves, not via who happened to click "create").
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    name = models.CharField(max_length=200, help_text='Internal, organization-facing name (e.g. "Ramadan Poster").')
    template = models.CharField(max_length=20, choices=Template.choices)
    # The full serializable canvas document -- {version, width, height,
    # background, elements: [...]}. Never just a generated PNG: this is
    # what makes the poster re-editable. See fundraising.md for the element
    # schema (static vs. binding-tagged dynamic elements).
    design = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Poster'
        verbose_name_plural = 'Posters'
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(destination_type=DestinationType.CAMPAIGN, campaign__isnull=False, organization__isnull=True)
                    | models.Q(destination_type=DestinationType.ORGANIZATION, campaign__isnull=True, organization__isnull=False)
                ),
                name='poster_exactly_one_destination',
            ),
        ]

    def __str__(self):
        return self.name


class PosterImage(BaseModel):
    """A user-uploaded image placed onto a poster canvas -- separate from
    the destination's own cover image (which is referenced by URL, not
    re-uploaded here). Kept as real rows (not inline base64 in `design`) so
    uploads go through the same validated/compressed upload path as every
    other image in this codebase (see image_compression.PROFILES'
    'poster_image' entry) instead of bloating the design JSON blob."""
    poster = models.ForeignKey(Poster, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to=poster_image_path)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Image for {self.poster.name}'


class Embed(BaseModel):
    class Layout(models.TextChoices):
        CARD = 'card', 'Card'
        COMPACT = 'compact', 'Compact'
        WIDE = 'wide', 'Wide'
        HORIZONTAL = 'horizontal', 'Horizontal'
        PROGRESS_FOCUSED = 'progress_focused', 'Progress-focused'

    destination_type = models.CharField(max_length=20, choices=DestinationType.choices)
    # Same CASCADE/PROTECT reasoning as Poster above.
    campaign = models.ForeignKey(
        'campaigns.Campaign', on_delete=models.CASCADE, null=True, blank=True, related_name='embeds',
    )
    organization = models.ForeignKey(
        'users.Organization', on_delete=models.PROTECT, null=True, blank=True, related_name='embeds',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    name = models.CharField(max_length=200, help_text='Internal, organization-facing name (e.g. "Homepage Donation").')
    layout = models.CharField(max_length=20, choices=Layout.choices, default=Layout.CARD)
    # Content/appearance settings -- title/description overrides, donate
    # button text, primary/background/text/button colors, border radius,
    # font sizing/spacing. See fundraising.md for the full shape. Kept as
    # one JSON blob (not individual columns) since this is genuinely
    # free-form presentation config, same reasoning as Poster.design.
    configuration = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Embed'
        verbose_name_plural = 'Embeds'
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(destination_type=DestinationType.CAMPAIGN, campaign__isnull=False, organization__isnull=True)
                    | models.Q(destination_type=DestinationType.ORGANIZATION, campaign__isnull=True, organization__isnull=False)
                ),
                name='embed_exactly_one_destination',
            ),
        ]

    def __str__(self):
        return self.name


class ShareLink(BaseModel):
    """A durable, short redirect for a Poster's QR code -- deliberately
    scoped to posters only, not a general-purpose platform-wide URL
    shortener. Exists because a printed/exported poster's QR code must keep
    working even if the destination's slug changes later; the redirect
    always resolves the *current* destination URL at scan time rather than
    baking in whatever URL was current when the poster was designed.

    Extensible in the narrow sense the spec asked for (deactivate, swap
    which poster a code points at, count scans) -- not a generic analytics
    platform. If Embed or some other feature ever needs a short link of its
    own, that's a deliberate follow-up decision, not something this model
    should quietly grow a generic `content_type`/`object_id` pair to cover
    pre-emptively.
    """
    poster = models.OneToOneField(Poster, on_delete=models.CASCADE, related_name='share_link')
    # Short, unique, generated in the service layer at creation time -- same
    # convention as Donation.payment_reference / Payout.reference (see
    # .claude/backend/models.md).
    code = models.CharField(max_length=12, unique=True)
    click_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'/q/{self.code} -> {self.poster.name}'
