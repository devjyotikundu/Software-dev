"""Security response headers not covered by Django's SecurityMiddleware."""
from django.conf import settings


def build_csp(request):
    host = request.get_host()
    sources = settings.CSP_SOURCES
    directives = {
        "default-src": ["'self'"],
        "script-src": ["'self'", *sources["scripts"]],          # no inline scripts anywhere
        "style-src": ["'self'", *sources["styles"]],
        "style-src-attr": ["'unsafe-inline'"],                    # progress bars use style="width:…"
        "font-src": ["'self'", *sources["fonts"]],
        "img-src": ["'self'", "data:"],
        "connect-src": ["'self'", f"wss://{host}", f"ws://{host}"],  # this site's WebSockets only
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'none'"],
    }
    return "; ".join(f"{name} {' '.join(values)}" for name, values in directives.items())


class SecurityHeadersMiddleware:
    """Content-Security-Policy and Permissions-Policy on every page.

    The Django admin is left out of the CSP because some of its widgets use
    inline JavaScript; it is staff-only and behind its own login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        if not request.path.startswith(f"/{settings.ADMIN_URL}"):
            header = "Content-Security-Policy-Report-Only" if settings.CSP_REPORT_ONLY else "Content-Security-Policy"
            response.headers.setdefault(header, build_csp(request))
        return response
