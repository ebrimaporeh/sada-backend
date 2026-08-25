"""Upload path functions for model ImageFields.

Keeps uploads organized by owner/slug and timestamped to the microsecond,
instead of Django's default flat "upload_to/original-filename.ext" (which
gives no browsable structure and silently suffixes colliding filenames).
Microsecond precision matters here specifically because several of these
fields are uploaded in pairs or batches in the same request — verification
front/back photos, campaign gallery images — where second-level timestamps
could collide.
"""
from django.utils import timezone


def _ext(filename: str) -> str:
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'


def _timestamp() -> str:
    return timezone.now().strftime('%Y%m%d%H%M%S%f')


def user_avatar_path(instance, filename: str) -> str:
    return f'avatars/{instance.id}/{_timestamp()}.{_ext(filename)}'


def identity_photo_front_path(instance, filename: str) -> str:
    return f'verifications/{instance.user_id}/front_{_timestamp()}.{_ext(filename)}'


def identity_photo_back_path(instance, filename: str) -> str:
    return f'verifications/{instance.user_id}/back_{_timestamp()}.{_ext(filename)}'


def organization_logo_path(instance, filename: str) -> str:
    # instance is an Organization -- no owning user any more (an org has
    # members, not a single owner), so this groups by the org's own id.
    return f'organizations/{instance.id}/logo_{_timestamp()}.{_ext(filename)}'


# Kept only because historical migrations (0014_alter_identityverification_
# id_photo_back_and_more) reference these by name -- Django imports every
# migration module to build the graph, so removing a upload_to function a
# past migration points to breaks makemigrations/migrate entirely, even
# though OrganizationVerification.contact_id_photo_front/back no longer
# exist as of migration 0021. Do not call these from current code.
def organization_contact_id_front_path(instance, filename: str) -> str:
    return f'org_verifications/{instance.organization_id}/contact_id_front_{_timestamp()}.{_ext(filename)}'


def organization_contact_id_back_path(instance, filename: str) -> str:
    return f'org_verifications/{instance.organization_id}/contact_id_back_{_timestamp()}.{_ext(filename)}'


def organization_registration_document_path(instance, filename: str) -> str:
    # instance is an OrganizationVerification -- groups by the org being
    # verified, not by submitted_by (whoever happened to submit this
    # particular request may not be who submits the next one).
    return f'org_verifications/{instance.organization_id}/registration_document_{_timestamp()}.{_ext(filename)}'


def organization_photo_path(instance, filename: str) -> str:
    return f'org_verifications/{instance.organization_id}/organization_photo_{_timestamp()}.{_ext(filename)}'


def category_image_path(instance, filename: str) -> str:
    return f'categories/{instance.slug}/{_timestamp()}.{_ext(filename)}'


def campaign_cover_image_path(instance, filename: str) -> str:
    return f'campaigns/{instance.slug}/cover_{_timestamp()}.{_ext(filename)}'


def campaign_gallery_image_path(instance, filename: str) -> str:
    return f'campaigns/{instance.campaign.slug}/gallery/{_timestamp()}.{_ext(filename)}'


def campaign_update_image_path(instance, filename: str) -> str:
    return f'campaigns/{instance.update.campaign.slug}/updates/{_timestamp()}.{_ext(filename)}'


def site_logo_path(instance, filename: str) -> str:
    return f'branding/logo_{_timestamp()}.{_ext(filename)}'


def site_logo_with_background_path(instance, filename: str) -> str:
    return f'branding/logo_with_background_{_timestamp()}.{_ext(filename)}'
