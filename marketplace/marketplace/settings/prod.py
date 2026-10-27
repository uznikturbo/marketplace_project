"""Production settings.

This is the default module for WSGI/ASGI and Celery. It disables ``DEBUG``,
requires a real secret key and enables the HTTPS-related security settings.

Security flags can be relaxed through the environment while a deployment is
being set up (for example, before a TLS certificate is ready), but the safe
default is to keep them on.
"""

from .base import *  # noqa: F401,F403
from .base import env_bool, env_int, load_secret_key

DEBUG = False
SECRET_KEY = load_secret_key(debug=False)

# Redirect every plain-HTTP request to HTTPS. The reverse proxy must send
# X-Forwarded-Proto, which SECURE_PROXY_SSL_HEADER in base.py already trusts.
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)

# HSTS. Start with a smaller value (for example 3600) and raise it once HTTPS
# is known to work for every subdomain.
SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", True
)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", True)

# Cookies must never travel over plain HTTP in production.
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", True)

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
