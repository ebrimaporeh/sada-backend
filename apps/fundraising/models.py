"""Fundraising Studio -- Poster Studio and Embed Studio.

Two independently-managed distribution/presentation tools, both resolved
through FundraisingDestination (see services/fundraising_destination.py)
rather than introducing a new fundraising/destination concept of their own.
Poster and Embed are deliberately separate model classes (not a shared
generic "Studio item" base) -- see .claude/backend/fundraising.md for the
full architecture writeup.

They no longer share the same destination shape. Poster still points at
exactly one of the platform's two donation destinations (Organization or
Campaign) via the destination_type/campaign/organization field trio and its
CheckConstraint, mirroring apps.donations.models.Donation's own "exactly
one destination" pattern. Embed is organization-scoped only (one per org,
via a OneToOneField) and instead renders a *gallery* of destinations
resolved at read time -- see Embed's own docstring and
fundraising_destination.resolve_embed_gallery_destinations().
"""
from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from utils.upload_paths import poster_image_path


class DestinationType(models.TextChoices):
    """Poster's destination trio -- a Poster points at exactly one of the
    platform's two donation destinations (Organization or Campaign) via
    this value + the campaign/organization FK pair below, both resolved
    through services/fundraising_destination.py::resolve_destination().

    Embed no longer uses this: an Embed is always organization-scoped (see
    Embed below) -- its gallery of destinations is resolved via
    fundraising_destination.resolve_embed_gallery_destinations() instead,
    which still calls resolve_destination() per item under the hood, so
    this enum's values stay the vocabulary both paths share."""
    ORGANIZATION = 'organization', 'Organization'
    CAMPAIGN = 'campaign', 'Campaign'


class Poster(BaseModel):
    class Template(models.TextChoices):
        """Size/aspect-ratio choice, not a design style -- every template
        renders the same composition (destination's cover photo full-bleed,
        dark scrim, title/org/description + QR anchored bottom-left, see
        the frontend's templateCompositions.js), just at a different frame
        shape matched to how people actually share it: a square feed post,
        a vertical story/status, or a wide link-preview banner."""
        SQUARE = 'square', 'Square'
        STORY = 'story', 'Story'
        WIDE = 'wide', 'Wide'

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
    """Exactly one Embed per Organization (enforced by the OneToOneField
    below) -- unlike Poster, an Embed is never per-campaign. Instead it
    renders a gallery of everything the organization has currently opted
    into showing: the organization itself (Organization.show_in_embed) plus
    every ACTIVE campaign with Campaign.show_in_embed set. See
    services/fundraising_destination.py::resolve_embed_gallery_destinations
    for how that list is built, and .claude/backend/fundraising.md for the
    full rationale -- this replaced an earlier per-campaign/per-org model
    that required a separate embed (and manual upkeep) per destination."""
    class Layout(models.TextChoices):
        CARD = 'card', 'Card'
        COMPACT = 'compact', 'Compact'
        WIDE = 'wide', 'Wide'
        HORIZONTAL = 'horizontal', 'Horizontal'
        PROGRESS_FOCUSED = 'progress_focused', 'Progress-focused'

    # One embed per org, at the DB level. No hard-delete path exists for
    # Organization anywhere in this codebase (see Poster's own comment
    # above) -- PROTECT is defensive for the same reason.
    organization = models.OneToOneField(
        'users.Organization', on_delete=models.PROTECT, related_name='embed',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    name = models.CharField(max_length=200, help_text='Internal, organization-facing name (e.g. "Homepage Donation").')
    # Applies uniformly to every destination card in the gallery -- there's
    # only one Embed per org, so there's no per-destination layout choice.
    layout = models.CharField(max_length=20, choices=Layout.choices, default=Layout.CARD)
    # Content/appearance settings -- donate button text, background/text/
    # button colors, card corner radius, button corner radius, curated
    # font-family key. See fundraising.md for the full shape. Kept as one
    # JSON blob (not individual columns) since this is genuinely free-form
    # presentation config, same reasoning as Poster.design.
    configuration = models.JSONField(default=dict, blank=True)
    # Where to send a donor back to once they finish donating through this
    # embed (e.g. the embedder's homepage) -- set by the embed's own owner,
    # never by anything a donor's request supplies. Donation.source_url
    # freezes a copy of this at donation-creation time (see
    # donation_service.create_donation) so later edits here don't
    # retroactively change where a past donor's success page points.
    # Optional: blank means the success page behaves as if this embed
    # didn't exist -- no return-to-site prompt.
    return_url = models.URLField(max_length=2000, blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Embed'
        verbose_name_plural = 'Embeds'

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
