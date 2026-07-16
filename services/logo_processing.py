"""Normalizes admin-uploaded site logos to a standard size and format.

Uploaded logo files land in wildly inconsistent shapes — the most common
case being a small wordmark centered in a much larger padded canvas
(e.g. a 500x500 square where the actual artwork is only 90px tall in the
middle). Since the frontend sizes logos by height (`h-8`, `h-9`, ...),
that padding makes the visible artwork render tiny regardless of what
CSS class is applied — there's no fixed height that fixes a variable,
unpredictable amount of built-in whitespace.

This trims each upload to its actual artwork's bounding box, adds a
small consistent margin back, caps it at one standard max size, and
always re-encodes as WebP (still fully supports the transparency this
needs) — so every uploaded logo behaves the same in the header/footer/
sidebar regardless of what canvas size or file type it arrived in.
"""
import io
from PIL import Image, ImageChops
from django.core.files.base import ContentFile

STANDARD_MAX_WIDTH = 800
STANDARD_MAX_HEIGHT = 240
PADDING_RATIO = 0.06  # breathing room around the trimmed artwork, relative to its largest side
MIN_PADDING_PX = 4
# Compressed/re-saved PNGs are rarely a perfectly flat background — corner
# pixels can drift a few values from the "true" background color even with
# no visible noise. Below this per-pixel difference is treated as background,
# not content, or getbbox() would trim to nothing (or the whole canvas).
BACKGROUND_TOLERANCE = 24


def _thresholded_bbox(mask: Image.Image, threshold: int = BACKGROUND_TOLERANCE) -> tuple:
    return mask.point(lambda v: 255 if v > threshold else 0).getbbox()


def _detect_bbox_and_background(image: Image.Image):
    """Returns (bbox, background_rgba). `background_rgba` is None when the
    image has real transparency (padding is trimmed to alpha); otherwise
    it's the solid corner color the artwork sits on (padding is trimmed
    against that color, e.g. a logo flattened onto white)."""
    rgba = image.convert('RGBA')
    alpha = rgba.getchannel('A')
    if alpha.getextrema()[0] < 255:
        bbox = _thresholded_bbox(alpha) or (0, 0, rgba.width, rgba.height)
        return bbox, None

    background_color = rgba.getpixel((0, 0))
    background = Image.new('RGBA', rgba.size, background_color)
    # Compare on RGB (as grayscale) — the alpha bands are identical (both
    # fully opaque) so an RGBA diff's getbbox() would look at alpha alone
    # and find nothing, regardless of how different the actual colors are.
    diff = ImageChops.difference(rgba.convert('RGB'), background.convert('RGB')).convert('L')
    bbox = _thresholded_bbox(diff) or (0, 0, rgba.width, rgba.height)
    return bbox, background_color


def process_logo_image(uploaded_file, transparent_padding: bool) -> ContentFile:
    """Trims padding, re-pads consistently, resizes to the standard max
    size, and re-encodes as WebP.

    `transparent_padding=True` for the logo meant to sit on arbitrary
    surfaces (padding becomes transparent); `False` for the logo meant to
    keep its own solid backing (padding is filled with its background
    color, so it still reads as "on a card" rather than floating).
    """
    image = Image.open(uploaded_file)
    bbox, background_color = _detect_bbox_and_background(image)
    trimmed = image.convert('RGBA').crop(bbox)

    pad = max(int(max(trimmed.size) * PADDING_RATIO), MIN_PADDING_PX)
    fill = (0, 0, 0, 0) if transparent_padding else (background_color or (255, 255, 255, 255))
    canvas = Image.new('RGBA', (trimmed.width + pad * 2, trimmed.height + pad * 2), fill)
    canvas.paste(trimmed, (pad, pad), trimmed)

    scale = min(STANDARD_MAX_WIDTH / canvas.width, STANDARD_MAX_HEIGHT / canvas.height, 1)
    if scale < 1:
        canvas = canvas.resize((round(canvas.width * scale), round(canvas.height * scale)), Image.LANCZOS)

    buffer = io.BytesIO()
    canvas.save(buffer, format='WEBP', quality=95, method=6)
    return ContentFile(buffer.getvalue(), name='logo.webp')
