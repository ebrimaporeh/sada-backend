from django.db.models import Q
from django.shortcuts import get_object_or_404

from apps.fundraising.models import Embed
import services.fundraising_destination as fundraising_destination


def get_owner_embeds(user):
    """Mirrors poster_service.get_owner_posters -- see its docstring."""
    from apps.organizations.models import OrganizationMembership
    org_ids = OrganizationMembership.objects.filter(user=user).values_list('organization_id', flat=True)
    return Embed.objects.filter(
        Q(campaign__owner=user, campaign__organization__isnull=True)
        | Q(campaign__organization_id__in=org_ids)
        | Q(organization_id__in=org_ids)
    ).select_related('campaign', 'organization').distinct()


def get_owner_embed(user, embed_id) -> Embed:
    embed = get_object_or_404(Embed, pk=embed_id)
    fundraising_destination.check_destination_manage_access(
        user, destination_type=embed.destination_type, campaign=embed.campaign, organization=embed.organization,
    )
    return embed


def get_public_embed(embed_id) -> Embed:
    """Backs the public, AllowAny embed data endpoint. Inactive embeds still
    resolve here (the view decides how to render an inactive state,
    per the spec's "display an appropriate inactive state" requirement)
    rather than 404ing outright -- a site that already installed the
    iframe should see a clear "no longer active" message, not a broken
    embed with no explanation."""
    return get_object_or_404(Embed.objects.select_related('campaign', 'campaign__organization', 'organization'), pk=embed_id)


def create_embed(user, *, destination_type, campaign=None, organization=None, name, layout=None, configuration=None, return_url=None) -> Embed:
    fundraising_destination.check_destination_manage_access(
        user, destination_type=destination_type, campaign=campaign, organization=organization,
    )
    return Embed.objects.create(
        destination_type=destination_type, campaign=campaign, organization=organization,
        created_by=user, name=name, layout=layout or Embed.Layout.CARD, configuration=configuration or {},
        return_url=return_url or '',
    )


def update_embed(user, embed: Embed, **fields) -> Embed:
    """Fields typically: name, layout, configuration. Destination is
    deliberately not updatable here -- same reasoning as
    poster_service.update_poster."""
    fundraising_destination.check_destination_manage_access(
        user, destination_type=embed.destination_type, campaign=embed.campaign, organization=embed.organization,
    )
    for field, value in fields.items():
        setattr(embed, field, value)
    embed.save()
    return embed


def duplicate_embed(user, embed: Embed) -> Embed:
    fundraising_destination.check_destination_manage_access(
        user, destination_type=embed.destination_type, campaign=embed.campaign, organization=embed.organization,
    )
    return Embed.objects.create(
        destination_type=embed.destination_type, campaign=embed.campaign, organization=embed.organization,
        created_by=user, name=f'{embed.name} (Copy)', layout=embed.layout, configuration=embed.configuration,
        is_active=False,  # a duplicate starts inactive -- avoid two "live" embeds with identical config by accident
    )


def set_embed_active(user, embed: Embed, is_active: bool) -> Embed:
    fundraising_destination.check_destination_manage_access(
        user, destination_type=embed.destination_type, campaign=embed.campaign, organization=embed.organization,
    )
    embed.is_active = is_active
    embed.save()
    return embed


def delete_embed(user, embed: Embed) -> None:
    fundraising_destination.check_destination_manage_access(
        user, destination_type=embed.destination_type, campaign=embed.campaign, organization=embed.organization,
    )
    embed.delete()
