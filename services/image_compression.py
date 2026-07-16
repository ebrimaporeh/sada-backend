"""Compresses and standardizes uploaded images to WebP.

The frontend already compresses images before upload (see
src/utils/imageCompression.js) — this exists as the backend half of
that system, not a duplicate of it: it re-validates rather than always
redoing the heavy lifting, but guarantees every image stored ends up
WebP and within its profile's size bounds regardless of what actually
uploaded it (a client that skipped the JS step, a direct API call, a
future mobile app). "Already compressed" is a byte-size-per-megapixel
heuristic — genuinely compressed photos land well under this; a raw
camera photo or a source PNG sit far above it.
"""
import io
from PIL import Image
from django.core.files.base import ContentFile

# (max_dimension, quality-if-recompressing) per upload purpose. Avatars get
# a larger dimension and higher quality than other "utility" images
# specifically because the campaigners masonry grid displays them large as
# the tile's main content, not just as a small nav-bar icon — a size/quality
# tuned for a 32px avatar chip would look visibly soft blown up that large.
PROFILES = {
    'avatar':           {'max_dimension': 1600, 'quality': 90},
    'campaign_cover':   {'max_dimension': 1920, 'quality': 85},
    'campaign_gallery': {'max_dimension': 1920, 'quality': 85},
    'campaign_update':  {'max_dimension': 1600, 'quality': 82},
    'category':         {'max_dimension': 800,  'quality': 82},
    'document':         {'max_dimension': 2000, 'quality': 90},
}
DEFAULT_PROFILE = 'campaign_gallery'

# A well-compressed WebP/JPEG photo typically lands well under this; a raw
# unprocessed upload sits far above it.
ALREADY_COMPRESSED_BYTES_PER_MEGAPIXEL = 300_000


def _megapixels(image: Image.Image) -> float:
    return max((image.width * image.height) / 1_000_000, 0.01)


def _is_already_compressed(uploaded_file, image: Image.Image) -> bool:
    return (uploaded_file.size / _megapixels(image)) <= ALREADY_COMPRESSED_BYTES_PER_MEGAPIXEL


def _rename_to_webp(filename: str) -> str:
    base = filename.rsplit('.', 1)[0] if '.' in filename else filename
    return f'{base}.webp'


def process_image(uploaded_file, profile: str = DEFAULT_PROFILE) -> ContentFile:
    """Returns a WebP-encoded ContentFile for `uploaded_file`.

    If the file already looks sufficiently compressed, only the format
    changes (no resize, near-lossless quality) — the frontend already
    sized it appropriately. Otherwise it's resized to the profile's max
    dimension and encoded at the profile's quality, same as if the
    frontend compression step had run.
    """
    settings_ = PROFILES.get(profile, PROFILES[DEFAULT_PROFILE])
    image = Image.open(uploaded_file)
    already_compressed = _is_already_compressed(uploaded_file, image)

    if image.mode not in ('RGB', 'RGBA'):
        image = image.convert('RGBA' if 'transparency' in image.info else 'RGB')

    if not already_compressed:
        width, height = image.size
        scale = min(settings_['max_dimension'] / max(width, height), 1)
        if scale < 1:
            image = image.resize((round(width * scale), round(height * scale)), Image.LANCZOS)

    quality = settings_['quality'] if not already_compressed else min(settings_['quality'] + 8, 95)

    buffer = io.BytesIO()
    image.save(buffer, format='WEBP', quality=quality, method=6)
    return ContentFile(buffer.getvalue(), name=_rename_to_webp(getattr(uploaded_file, 'name', 'image.webp')))
