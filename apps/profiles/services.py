"""Profile rules and operations. Views and forms call these; no request handling here."""
from io import BytesIO

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import UserLanguage

# ---------------------------------------------------------------- languages
MAX_LANGUAGES_PER_ROLE = 3  # keeps profiles focused and matching meaningful


def language_limits_reached(user):
    counts = {role: 0 for role in UserLanguage.Role.values}
    for role in user.languages.values_list("role", flat=True):
        counts[role] += 1
    return {role: count >= MAX_LANGUAGES_PER_ROLE for role, count in counts.items()}


def can_remove_language(user_language):
    """A profile always keeps at least one native and one learning language."""
    return (
        UserLanguage.objects.filter(user_id=user_language.user_id, role=user_language.role)
        .exclude(pk=user_language.pk)
        .exists()
    )


@transaction.atomic
def remove_language(user_language):
    # Lock this user's rows so two simultaneous removals can't both pass the check.
    list(UserLanguage.objects.select_for_update().filter(user_id=user_language.user_id))
    if not can_remove_language(user_language):
        role = user_language.get_role_display().lower()
        raise ValidationError(f"Keep at least one {role} language on your profile.")
    user_language.delete()


# ------------------------------------------------------------------ avatars
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_SIZE = 400                   # stored as a 400×400 square
AVATAR_MAX_PIXELS = 40_000_000      # rejects decompression bombs early
AVATAR_FORMATS = {"JPEG", "PNG", "WEBP"}


def process_avatar(uploaded):
    """Validate an uploaded image and re-encode it as a clean square JPEG.

    Re-encoding strips EXIF data (including GPS location) and anything
    hidden in the original file. Raises ValidationError for anything that
    isn't a real JPEG, PNG or WebP image within the limits.
    """
    if uploaded.size > AVATAR_MAX_BYTES:
        raise ValidationError("Choose an image smaller than 2 MB.")
    uploaded.seek(0)
    try:
        with Image.open(uploaded) as image:
            if image.format not in AVATAR_FORMATS:
                raise ValidationError("Use a JPEG, PNG or WebP image.")
            if image.width * image.height > AVATAR_MAX_PIXELS:
                raise ValidationError("This image's dimensions are too large.")
            image.load()
            image = ImageOps.exif_transpose(image)  # respect phone rotation
            image = image.convert("RGBA")
            flattened = Image.new("RGB", image.size, (255, 255, 255))
            flattened.paste(image, mask=image.getchannel("A"))
            square = ImageOps.fit(
                flattened, (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS
            )
            buffer = BytesIO()
            square.save(buffer, format="JPEG", quality=85, optimize=True)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise ValidationError("This file isn't an image we can read.")
    return ContentFile(buffer.getvalue(), name="avatar.jpg")


def replace_avatar(profile, new_file=None, *, remove=False):
    """Swap or clear the avatar, deleting the old file only after the database commits."""
    old_name = profile.avatar.name if profile.avatar else ""
    if new_file is not None:
        profile.avatar.save(new_file.name, new_file, save=False)
    elif remove:
        profile.avatar = ""
    else:
        return
    profile.save(update_fields=["avatar", "updated_at"])
    if old_name and old_name != profile.avatar.name:
        storage = profile.avatar.storage
        transaction.on_commit(lambda: storage.delete(old_name))
