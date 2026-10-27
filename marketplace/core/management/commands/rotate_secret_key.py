from django.core.management.base import BaseCommand

from core.secret_key import rotate_secret_key


class Command(BaseCommand):
    help = "Generate a new Django SECRET_KEY and write it to SECRET_KEY_FILE."

    def handle(self, *args, **options):
        path = rotate_secret_key()
        self.stdout.write(
            self.style.SUCCESS(f"New SECRET_KEY written to {path}")
        )
        self.stdout.write(
            self.style.WARNING(
                "Restart the application to load the new key. "
                "All sessions, CSRF tokens and signed links will be invalidated."
            )
        )
