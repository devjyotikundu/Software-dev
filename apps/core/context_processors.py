from django.conf import settings


def site(request):
    """Values every template needs."""
    return {"site_name": settings.SITE_NAME}
