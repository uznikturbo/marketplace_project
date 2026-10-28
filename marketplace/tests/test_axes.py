from axes.models import AccessAttempt
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from .base import BaseTestCase, make_user


@override_settings(
    AXES_ENABLED=True,
    AXES_FAILURE_LIMIT=2,
    AXES_COOLOFF_TIME=None,
    AXES_LOCKOUT_PARAMETERS=["username", "ip_address"],
    AXES_RESET_ON_SUCCESS=True,
)
class AxesLoginTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        AccessAttempt.objects.all().delete()
        self.user = make_user()
        self.url = reverse("login")

    def _login(self, password):
        return self.client.post(
            self.url,
            {"username": self.user.number, "password": password},
        )

    def test_login_is_locked_after_failure_limit(self):
        self._login("wrong-password")
        self._login("wrong-password")

        response = self._login("wrong-password")

        self.assertEqual(response.status_code, 429)

    def test_locked_user_cannot_login_with_correct_password(self):
        self._login("wrong-password")
        self._login("wrong-password")

        response = self._login("StrongPass123!")

        self.assertEqual(response.status_code, 429)
        self.assertNotIn("_auth_user_id", self.client.session)

    @override_settings(AXES_FAILURE_LIMIT=3)
    def test_successful_login_resets_failure_counter(self):
        self._login("wrong-password")
        response = self._login("StrongPass123!")

        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)
