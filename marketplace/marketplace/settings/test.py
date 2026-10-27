"""Settings used by the test suite and CI.

They keep the real database configuration but replace Redis with an in-memory
cache, use a fast password hasher and print e-mails to memory. This means the
tests do not need Redis or an SMTP server.
"""

from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "test-secret-key-not-for-production"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "marketplace-tests",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

SECURE_SSL_REDIRECT = False
