"""Helpers for rotating the Django ``SECRET_KEY``.

The key is stored in a dedicated file (``settings.SECRET_KEY_FILE``) that is
read at startup. Rotating it writes a new key atomically, but running
processes keep the old key until they are restarted: Django reads
``SECRET_KEY`` only once, when settings are loaded.
"""

import logging
import os
import stat
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.utils import get_random_secret_key

logger = logging.getLogger(__name__)


def get_secret_key_path() -> Path:
    """Return the configured path of the secret key file."""
    return Path(settings.SECRET_KEY_FILE)


def rotate_secret_key() -> Path:
    """Generate a new secret key and atomically store it on disk.

    Returns the path of the written key file.
    """
    path = get_secret_key_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    new_key = get_random_secret_key()
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".secret-key-")
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(new_key + "\n")
        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    logger.warning(
        "Django SECRET_KEY rotated and written to %s. Restart the application "
        "to pick up the new key; existing sessions, CSRF tokens and signed "
        "links will be invalidated.",
        path,
    )
    return path
