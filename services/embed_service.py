from django.shortcuts import get_object_or_404

from apps.fundraising.models import DestinationType, Embed
from apps.users.models import Organization
import services.fundraising_destination as fundraising_destination


def get_or_create_org_embed(user, organization: Organization) -> Embed:
    """The only way an Embed comes into existence -- there's no separate
    "create" verb (see EmbedCreateSerializer's removal): visiting the
    Studio, or hitting the public endpoint's owner-facing counterpart, for
    an organization that doesn't have one yet just makes one, blank, on the
    spot. Idempotent -- calling this twice for the same organization always
    returns the same row, enforced by Embed.organization's OneToOneField."""
    fundraising_destination.check_destination_manage_access(
        user, destination_type=DestinationType.ORGANIZATION, organization=organization,
    )
    embed, _ = Embed.objects.get_or_create(
        organization=organization,
        defaults={'created_by': user, 'name': f'{organization.organization_name} Embed'},
    )
    return embed


def get_owner_org_embed(user, organization_id) -> Embed:
    organization = get_object_or_404(Organization, pk=organization_id)
    return get_or_create_org_embed(user, organization)


def get_owner_embed(user, embed_id) -> Embed:
    embed = get_object_or_404(Embed.objects.select_related('organization'), pk=embed_id)
    fundraising_destination.check_destination_manage_access(
        user, destination_type=DestinationType.ORGANIZATION, organization=embed.organization,
    )
    return embed


def get_public_embed(embed_id) -> Embed:
    """Backs the public, AllowAny embed data endpoint. Inactive embeds still
    resolve here (the view decides how to render an inactive state, per the
    spec's "display an appropriate inactive state" requirement) rather than
    404ing outright -- a site that already installed the iframe should see
    a clear "no longer active" message, not a broken embed with no
    explanation."""
    return get_object_or_404(Embed.objects.select_related('organization'), pk=embed_id)


def update_embed(user, embed: Embed, **fields) -> Embed:
    """Fields typically: name, layout, configuration, return_url.
    Organization is deliberately not updatable here -- same reasoning as
    poster_service.update_poster not allowing a destination swap."""
    fundraising_destination.check_destination_manage_access(
        user, destination_type=DestinationType.ORGANIZATION, organization=embed.organization,
    )
    for field, value in fields.items():
        setattr(embed, field, value)
    embed.save()
    return embed


def set_embed_active(user, embed: Embed, is_active: bool) -> Embed:
    fundraising_destination.check_destination_manage_access(
        user, destination_type=DestinationType.ORGANIZATION, organization=embed.organization,
    )
    embed.is_active = is_active
    embed.save()
    return embed
