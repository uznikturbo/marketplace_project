from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse

from registration.tasks import send_sms_conf_task
from registration.utils import generate_code

from .base import BaseTestCase, make_user

User = get_user_model()


class GenerateCodeTests(BaseTestCase):
    def test_code_is_six_digit_string(self):
        code = generate_code()

        self.assertIsInstance(code, str)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_codes_are_not_constant(self):
        codes = {generate_code() for _ in range(20)}

        self.assertGreater(len(codes), 1)


class RegisterTests(BaseTestCase):
    def _payload(self, **overrides):
        payload = {
            "number": "+380501234567",
            "email": "newuser@example.com",
            "password1": "SuperSecret123!",
            "password2": "SuperSecret123!",
        }
        payload.update(overrides)
        return payload

    def test_register_page_renders(self):
        response = self.client.get(reverse("register"))

        self.assertEqual(response.status_code, 200)

    def test_successful_registration_logs_user_in(self):
        response = self.client.post(reverse("register"), self._payload())

        self.assertRedirects(response, reverse("home"))
        user = self.client.session.get("_auth_user_id")
        self.assertIsNotNone(user)

    def test_registration_normalizes_number(self):
        self.client.post(reverse("register"), self._payload(number="0501234567"))

        user = User.objects.get(email="newuser@example.com")
        self.assertEqual(user.number, "+380501234567")

    def test_duplicate_email_is_rejected(self):
        make_user(email="newuser@example.com")

        response = self.client.post(reverse("register"), self._payload())

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get("_auth_user_id"))

    def test_password_mismatch_is_rejected(self):
        response = self.client.post(
            reverse("register"),
            self._payload(password2="DifferentPassword123!"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get("_auth_user_id"))


class LoginTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.password = "StrongPass123!"
        self.user = make_user(password=self.password)

    def _login(self, **overrides):
        payload = {"username": self.user.number, "password": self.password}
        payload.update(overrides)
        return self.client.post(reverse("login"), payload)

    def test_login_page_renders(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)

    def test_successful_login_redirects_home(self):
        response = self._login()

        self.assertRedirects(response, reverse("home"))

    def test_safe_next_url_is_used(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.number,
                "password": self.password,
                "next": reverse("catalog"),
            },
        )

        self.assertRedirects(response, reverse("catalog"))

    def test_external_next_url_is_ignored(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.number,
                "password": self.password,
                "next": "https://evil.example.com/steal",
            },
        )

        self.assertRedirects(response, reverse("home"))

    def test_next_from_query_string_is_kept_in_context(self):
        response = self.client.get(reverse("login"), {"next": reverse("catalog")})

        self.assertEqual(response.context["next"], reverse("catalog"))

    def test_invalid_password_is_rejected(self):
        response = self._login(password="wrong-password")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get("_auth_user_id"))

    def test_unknown_user_is_rejected(self):
        response = self._login(username="+380500000000")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get("_auth_user_id"))


class SendSmsTaskTests(BaseTestCase):
    @override_settings(SMS_API_URL=None, SMS_API_KEY=None)
    @patch("registration.tasks.requests.post")
    def test_without_provider_logs_code_and_does_not_send(self, mock_post):
        with self.assertLogs("registration.tasks", level="WARNING") as logs:
            result = send_sms_conf_task("+380501112233", "123456")

        self.assertFalse(result)
        mock_post.assert_not_called()
        self.assertIn("123456", "\n".join(logs.output))

    @override_settings(SMS_API_URL="https://sms.example.com/send", SMS_API_KEY="secret")
    @patch("registration.tasks.requests.post")
    def test_sends_request_when_provider_is_configured(self, mock_post):
        mock_post.return_value = MagicMock()

        result = send_sms_conf_task("+380501112233", "123456")

        self.assertTrue(result)
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["api_key"], "secret")
        self.assertEqual(payload["to"], "+380501112233")
        self.assertIn("123456", payload["message"])
        self.assertEqual(mock_post.call_args.kwargs["timeout"], 10)

    @override_settings(SMS_API_URL="https://sms.example.com/send", SMS_API_KEY="secret")
    @patch("registration.tasks.requests.post")
    def test_network_error_is_propagated_for_retry(self, mock_post):
        import requests

        mock_post.side_effect = requests.RequestException("network down")

        # Celery re-raises the original error and schedules a retry.
        with self.assertLogs("registration.tasks", level="WARNING"):
            with self.assertRaises(requests.RequestException):
                send_sms_conf_task("+380501112233", "123456")

    @override_settings(SMS_API_URL="https://sms.example.com/send", SMS_API_KEY="secret")
    @patch("registration.tasks.requests.post")
    def test_http_error_is_propagated_for_retry(self, mock_post):
        import requests

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("500")
        mock_post.return_value = mock_response

        with self.assertLogs("registration.tasks", level="WARNING"):
            with self.assertRaises(requests.HTTPError):
                send_sms_conf_task("+380501112233", "123456")
