"""Storage backends for buckets other than the default public `media` one
configured in settings/base.py.

Organization verification documents (registration certificates, the
organization photo submitted alongside them) are sensitive and must never
be served from a public, permanently-accessible URL -- see
VerificationDocumentStorage below.
"""
from django.conf import settings
from storages.backends.s3 import S3Storage


class VerificationDocumentStorage(S3Storage):
    """Private Supabase bucket for organization verification documents.

    Reuses every connection setting already configured for the public
    `media` bucket in settings/base.py (access key, secret key, endpoint,
    region, addressing style) -- S3Storage.get_default_settings() falls
    back to AWS_S3_ACCESS_KEY_ID/AWS_S3_ENDPOINT_URL/etc. for any attribute
    not overridden below, and those are the same Supabase project either
    way, just a different bucket.

    `bucket_name` is a property (not a plain class attribute) so it's read
    fresh from settings on every access rather than baked in at import
    time -- this matters both for `override_settings` in tests and so a
    single `VerificationDocumentStorage()` instantiated with zero
    constructor args deconstructs to zero args in migrations (see
    apps/users/models.py) regardless of whether SUPABASE_VERIFICATION_BUCKET
    happens to be set in whichever environment generates the migration.

    `custom_domain = None` + `querystring_auth = True` is the entire
    difference from the public bucket's behavior: no permanent public-read
    URL path is ever built, and every `.url` call instead asks S3
    (Supabase's S3-compatible endpoint) for a presigned GET URL that
    expires in `querystring_expire` seconds. Never cache/store the result
    of `.url` -- call it fresh at request time, every time.
    """
    custom_domain = None
    querystring_auth = True
    querystring_expire = 300  # 5 minutes
    file_overwrite = True
    default_acl = None

    @property
    def bucket_name(self):
        return settings.SUPABASE_VERIFICATION_BUCKET


def get_verification_storage():
    """Storage for OrganizationVerification's document fields, or None
    (Django's configured default -- local disk in dev/test) when the
    private bucket isn't configured at all -- mirrors settings/base.py's
    fallback for the public `media` bucket when SUPABASE_STORAGE_BUCKET
    isn't set (e.g. running tests, or before a Supabase project exists)."""
    if not settings.SUPABASE_VERIFICATION_BUCKET:
        return None
    return VerificationDocumentStorage()
