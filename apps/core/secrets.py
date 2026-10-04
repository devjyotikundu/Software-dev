"""Plain-Python helpers used while settings load (no Django imports here)."""


def weak_secret_key(key):
    """True if a SECRET_KEY is unsuitable for production."""
    key = key or ""
    return len(key) < 50 or key.startswith("django-insecure") or len(set(key)) < 5
