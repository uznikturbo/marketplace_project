"""Development settings.

This is the default module for ``manage.py``. It enables ``DEBUG`` and the
Django Debug Toolbar (when ``django-debug-toolbar`` is installed) and never
forces HTTPS, so it is safe to use with ``runserver`` over plain HTTP.

Run production-like checks with::

    DJANGO_SETTINGS_MODULE=marketplace.settings.prod python manage.py check --deploy
"""

from .base import *  # noqa: F401,F403
from .base import load_secret_key

DEBUG = True
SECRET_KEY = load_secret_key(debug=True)

ALLOWED_HOSTS = sorted(
    {*ALLOWED_HOSTS, "localhost", "127.0.0.1", ".ngrok-free.app", ".ngrok.io"}
)
CSRF_TRUSTED_ORIGINS = sorted(
    {*CSRF_TRUSTED_ORIGINS, "https://*.ngrok-free.app"}
)
INTERNAL_IPS = ["127.0.0.1"]

# Print e-mails to the console instead of trying to reach an SMTP server.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# The development server is plain HTTP.
SECURE_SSL_REDIRECT = False

try:
    import debug_toolbar  # noqa: F401
except ImportError:  # pragma: no cover - optional development dependency
    pass
else:
    INSTALLED_APPS = [*INSTALLED_APPS, "debug_toolbar"]
    MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware", *MIDDLEWARE]
