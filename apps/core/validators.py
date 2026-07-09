from django.core.exceptions import ValidationError

MAX_IMAGE_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB


def validate_image_size(file):
    if file.size > MAX_IMAGE_UPLOAD_SIZE:
        raise ValidationError(f'Image must be smaller than {MAX_IMAGE_UPLOAD_SIZE // (1024 * 1024)}MB.')
