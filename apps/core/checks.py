"""System checks that catch deployment mistakes before users see them."""
from pathlib import Path

from django.conf import settings
from django.core.checks import Error, Tags, register

MANIFEST_BACKENDS = ("ManifestStaticFilesStorage", "CompressedManifestStaticFilesStorage")


@register(Tags.staticfiles, deploy=True)
def static_manifest_exists(app_configs=None, **kwargs):
    """With a manifest storage, collectstatic must have written staticfiles.json.

    Without it, the first {% static %} lookup raises "Missing staticfiles
    manifest entry" on every page. Runs with `manage.py check --deploy`.
    """
    backend = settings.STORAGES.get("staticfiles", {}).get("BACKEND", "")
    if not backend.endswith(MANIFEST_BACKENDS):
        return []
    manifest = Path(settings.STATIC_ROOT) / "staticfiles.json"
    if manifest.exists():
        return []
    return [Error(
        f"Static files manifest not found at {manifest}.",
        hint="Run `python manage.py collectstatic --noinput` with the same settings module the server "
             "uses (e.g. --settings=config.settings.production) during the build.",
        id="core.E001",
    )]

