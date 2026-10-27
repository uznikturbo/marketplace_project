import stat
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import override_settings

from core.secret_key import rotate_secret_key
from core.tasks import rotate_secret_key_task

from .base import BaseTestCase


class SecretKeyRotationTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.key_path = Path(self.tmp_dir.name) / "nested" / ".secret_key"

        override = override_settings(SECRET_KEY_FILE=self.key_path)
        override.enable()
        self.addCleanup(override.disable)

    def test_creates_key_file_with_restrictive_permissions(self):
        rotate_secret_key()

        self.assertTrue(self.key_path.exists())
        mode = stat.S_IMODE(self.key_path.stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_written_key_is_not_empty(self):
        rotate_secret_key()

        key = self.key_path.read_text().strip()

        self.assertGreaterEqual(len(key), 50)

    def test_each_rotation_generates_a_different_key(self):
        rotate_secret_key()
        first = self.key_path.read_text()
        rotate_secret_key()
        second = self.key_path.read_text()

        self.assertNotEqual(first, second)

    def test_task_rotates_the_key(self):
        result = rotate_secret_key_task()

        self.assertEqual(result, str(self.key_path))
        self.assertTrue(self.key_path.exists())

    def test_management_command_rotates_the_key(self):
        stdout = StringIO()

        call_command("rotate_secret_key", stdout=stdout)

        self.assertTrue(self.key_path.exists())
        self.assertIn(str(self.key_path), stdout.getvalue())

    def test_no_temporary_files_are_left_behind(self):
        rotate_secret_key()

        leftovers = list(self.key_path.parent.glob(".secret-key-*"))

        self.assertEqual(leftovers, [])
