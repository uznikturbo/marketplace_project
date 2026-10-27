from celery import shared_task

from .secret_key import rotate_secret_key


@shared_task
def rotate_secret_key_task():
    """Rotate the Django SECRET_KEY (scheduled by Celery beat)."""
    return str(rotate_secret_key())
