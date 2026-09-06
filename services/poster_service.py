import secrets
import string

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404

from apps.fundraising.models import Poster, PosterImage, ShareLink
import services.fundraising_destination as fundraising_destination

_CODE_ALPHABET = string.ascii_lowercase + string.digits
_CODE_LENGTH = 8


def _generate_share_code() -> str:
    for _ in range(10):
        code = ''.join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        if not ShareLink.objects.filter(code=code).exists():
            return code
    raise RuntimeError('Could not generate a unique share code after 10 attempts.')


def get_owner_posters(user):
    """Every poster this user can manage -- mirrors
    campaign_service.get_owner_campaigns' shape: their own individual
    campaigns' posters, plus every poster (campaign- or organization-
    destination) belonging to an organization they're currently a member
    of."""
    from apps.organizations.models import OrganizationMembership
    org_ids = OrganizationMembership.objects.filter(user=user).values_list('organization_id', flat=True)
    return Poster.objects.filter(
        Q(campaign__owner=user, campaign__organization__isnull=True)
        | Q(campaign__organization_id__in=org_ids)
        | Q(organization_id__in=org_ids)
    ).select_related('campaign', 'organization', 'share_link').distinct()


def get_owner_poster(user, poster_id) -> Poster:
    poster = get_object_or_404(Poster, pk=poster_id)
    fundraising_destination.check_destination_manage_access(
        user, destination_type=poster.destination_type, campaign=poster.campaign, organization=poster.organization,
    )
    return poster


@transaction.atomic
def create_poster(user, *, destination_type, campaign=None, organization=None, name, template, design=None) -> Poster:
    fundraising_destination.check_destination_manage_access(
        user, destination_type=destination_type, campaign=campaign, organization=organization,
    )
    poster = Poster.objects.create(
        destination_type=destination_type, campaign=campaign, organization=organization,
        created_by=user, name=name, template=template, design=design or {},
    )
    ShareLink.objects.create(poster=poster, code=_generate_share_code())
    return poster


def update_poster(user, poster: Poster, **fields) -> Poster:
    """Fields typically: name, design (autosave), status. Destination
    (destination_type/campaign/organization) is deliberately not
    updatable here -- changing what a poster points at is a "create a new
    one" operation, not an edit, so its dynamic-binding elements never
    silently start rendering a different destination's data underneath an
    unchanged design."""
    fundraising_destination.check_destination_manage_access(
        user, destination_type=poster.destination_type, campaign=poster.campaign, organization=poster.organization,
    )
    for field, value in fields.items():
        setattr(poster, field, value)
    poster.save()
    return poster


def duplicate_poster(user, poster: Poster) -> Poster:
    fundraising_destination.check_destination_manage_access(
        user, destination_type=poster.destination_type, campaign=poster.campaign, organization=poster.organization,
    )
    new_poster = Poster.objects.create(
        destination_type=poster.destination_type, campaign=poster.campaign, organization=poster.organization,
        created_by=user, name=f'{poster.name} (Copy)', template=poster.template, design=poster.design,
    )
    ShareLink.objects.create(poster=new_poster, code=_generate_share_code())
    return new_poster


def delete_poster(user, poster: Poster) -> None:
    fundraising_destination.check_destination_manage_access(
        user, destination_type=poster.destination_type, campaign=poster.campaign, organization=poster.organization,
    )
    poster.delete()


def upload_poster_image(user, poster: Poster, image_file) -> PosterImage:
    """A user-uploaded image for the editor's Image element -- separate
    from the destination's own cover image, which is referenced by URL and
    never re-uploaded here. Same permission gate and compression pattern as
    campaign_service.upload_cover."""
    fundraising_destination.check_destination_manage_access(
        user, destination_type=poster.destination_type, campaign=poster.campaign, organization=poster.organization,
    )
    if not image_file:
        raise ValueError('No image provided.')
    from services.image_compression import process_image
    return PosterImage.objects.create(poster=poster, image=process_image(image_file, profile='poster_image'))


def resolve_share_link(code: str) -> str:
    """Backs GET /q/<code>/ -- returns the destination's *current* public
    URL (not whatever URL was current when the poster was designed) and
    increments the scan counter. Raises Http404 (via get_object_or_404) for
    an unknown/deleted code -- a deleted poster CASCADEs its ShareLink, so a
    printed QR for a poster the owner later deleted simply 404s rather than
    resolving to stale data."""
    from django.db.models import F

    share_link = get_object_or_404(ShareLink.objects.select_related('poster__campaign', 'poster__organization'), code=code)
    ShareLink.objects.filter(pk=share_link.pk).update(click_count=F('click_count') + 1)
    poster = share_link.poster
    destination = fundraising_destination.resolve_destination(
        poster.destination_type, campaign=poster.campaign, organization=poster.organization,
    )
    return destination.public_url
