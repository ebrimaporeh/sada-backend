"""Fundraising Studio's shared destination resolver.

Poster Studio and Embed Studio both point at exactly one of the platform's
two existing donation destinations -- Organization or Campaign. This module
is the *only* place that branches on which one a given Poster/Embed points
at; poster_service.py and embed_service.py both call resolve_destination()
rather than re-implementing "if campaign else organization" themselves. No
new database model is introduced here -- FundraisingDestination is a plain,
non-persisted view over the existing Campaign/Organization rows, built from
data those models (and their own services) already expose.

Deliberately takes already-fetched Campaign/Organization instances rather
than fetching by id/slug itself -- ownership/membership access checks
(organization_service.check_campaign_access / require_permission) happen in
poster_service.py/embed_service.py, at the same layer every other
campaign/organization-mutating code path enforces them, not duplicated here.
"""
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Optional

from django.conf import settings


def _frontend_url(path: str) -> str:
    base = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
    return f'{base}{path}'


def _absolute_media_url(request, field) -> Optional[str]:
    if not field:
        return None
    if request is not None:
        return request.build_absolute_uri(field.url)
    return field.url


@dataclass
class FundraisingDestination:
    type: str  # DestinationType.ORGANIZATION or DestinationType.CAMPAIGN
    id: str
    title: str
    slug: str
    description: str
    cover_image_url: Optional[str]
    organization_name: Optional[str]
    organization_logo_url: Optional[str]
    currency: str
    goal: Optional[Decimal]
    raised: Optional[Decimal]
    progress_percent: Optional[int]
    donors_count: Optional[int]
    deadline: Optional[str]  # ISO date string, or None -- None means "no deadline"
    is_ongoing: bool  # True when there is genuinely no deadline concept (org) or deadline is None (campaign)
    public_url: str
    donation_url: str


def resolve_destination(destination_type: str, *, campaign=None, organization=None, request=None) -> FundraisingDestination:
    from apps.fundraising.models import DestinationType

    if destination_type == DestinationType.CAMPAIGN:
        if campaign is None:
            raise ValueError('campaign is required when destination_type is CAMPAIGN')
        org = campaign.organization
        return FundraisingDestination(
            type=DestinationType.CAMPAIGN,
            id=str(campaign.id),
            title=campaign.title,
            slug=campaign.slug,
            description=campaign.short_description,
            cover_image_url=_absolute_media_url(request, campaign.cover_image),
            organization_name=org.organization_name if org else None,
            organization_logo_url=_absolute_media_url(request, org.logo) if org else None,
            currency=campaign.currency,
            goal=campaign.goal,
            raised=campaign.raised,
            progress_percent=campaign.progress_percent,
            donors_count=campaign.donors_count,
            deadline=campaign.deadline.isoformat() if campaign.deadline else None,
            is_ongoing=campaign.deadline is None,
            public_url=_frontend_url(f'/campaigns/{campaign.slug}'),
            donation_url=_frontend_url(f'/donate/{campaign.slug}'),
        )

    if destination_type == DestinationType.ORGANIZATION:
        if organization is None:
            raise ValueError('organization is required when destination_type is ORGANIZATION')
        # Direct organization donations are open-ended by nature -- no
        # goal/deadline/progress concept exists for them today (see
        # OrganizationPublicDonateView/OrganizationPublicSerializer); don't
        # fabricate zeros here, leave these genuinely None so callers (the
        # poster/embed renderers) know not to show a progress bar at all.
        return FundraisingDestination(
            type=DestinationType.ORGANIZATION,
            id=str(organization.id),
            title=organization.organization_name,
            slug=organization.slug,
            description=organization.description,
            cover_image_url=_absolute_media_url(request, organization.cover_image),
            organization_name=organization.organization_name,
            organization_logo_url=_absolute_media_url(request, organization.logo),
            currency='GMD',
            goal=None,
            raised=None,
            progress_percent=None,
            donors_count=None,
            deadline=None,
            is_ongoing=True,
            public_url=_frontend_url(f'/give/{organization.slug}'),
            donation_url=_frontend_url(f'/give/{organization.slug}'),
        )

    raise ValueError(f'Unknown destination_type: {destination_type!r}')


def serialize_destination(poster_or_embed, request=None) -> dict:
    """Plain-dict shape of a Poster/Embed's resolved destination -- shared by
    poster_serializers.py and embed_serializers.py so neither has to import
    from the other for it (Poster and Embed otherwise share no code beyond
    this destination resolver, per the architecture doc)."""
    destination = resolve_destination(
        poster_or_embed.destination_type,
        campaign=poster_or_embed.campaign,
        organization=poster_or_embed.organization,
        request=request,
    )
    return asdict(destination)


def check_destination_manage_access(user, *, destination_type, campaign=None, organization=None) -> None:
    """The single place Poster/Embed create/update/delete/duplicate funnels
    through to authorize "can this user manage fundraising presentation
    material for this destination" -- poster_service.py and embed_service.py
    both call this rather than re-implementing the branch themselves.

    Campaign destinations: reuses organization_service.check_campaign_access
    with OrganizationPermission.EDIT_CAMPAIGN, exactly like any other
    campaign-presentation-editing action (e.g. campaign_service.upload_cover).

    Organization destinations: reuses OrganizationPermission.MANAGE_ORGANIZATION
    -- the same gate organization_service.upload_cover_image() already uses
    for the org's donation-page banner, the closest existing precedent to
    "edit this org's donation-page presentation assets". Deliberately
    re-implements the Http404-vs-403 split here (get_membership is None ->
    404, membership present but missing manage_organization -> 403) instead
    of calling organization_service.require_permission(), which only ever
    raises a flat 403 -- that's correct for require_permission's existing
    call sites (they already hold a resolved Organization the caller is
    known to belong to), but here the caller is probing an opaque
    Poster/Embed id that could belong to any organization, so the same
    anti-enumeration reasoning check_campaign_access already applies to
    campaigns should apply here too.
    """
    from django.http import Http404
    from rest_framework.exceptions import PermissionDenied

    from apps.fundraising.models import DestinationType
    from apps.organizations.permissions import OrganizationPermission
    import services.organization_service as organization_service

    if destination_type == DestinationType.CAMPAIGN:
        organization_service.check_campaign_access(user, campaign, OrganizationPermission.EDIT_CAMPAIGN)
        return

    membership = organization_service.get_membership(user, organization)
    if membership is None:
        raise Http404('Not found.')
    if OrganizationPermission.MANAGE_ORGANIZATION not in membership.role.permissions:
        raise PermissionDenied("You don't have permission to manage this organization's fundraising materials.")
