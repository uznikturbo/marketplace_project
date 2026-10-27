from unittest.mock import patch

from django.urls import reverse

from catalog.models import Cart

from .base import BaseTestCase


class HomeViewTests(BaseTestCase):
    def test_home_page_renders(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)

    def test_home_page_does_not_create_cart(self):
        self.client.get(reverse("home"))

        self.assertEqual(Cart.objects.count(), 0)


class HealthViewTests(BaseTestCase):
    def test_health_returns_ok(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"status": "ok", "database": "ok"}
        )

    def test_health_with_trailing_slash(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)

    @patch("core.views.connection")
    def test_health_returns_503_when_database_is_down(self, mock_connection):
        mock_connection.cursor.side_effect = Exception("database is down")

        with self.assertLogs("core.views", level="ERROR"):
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "error")


class FaviconTests(BaseTestCase):
    def test_favicon_is_served(self):
        response = self.client.get("/favicon.ico")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/x-icon")

    def test_base_template_links_favicon(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'rel="icon"')


class TimezoneMiddlewareTests(BaseTestCase):
    def test_valid_timezone_is_kept(self):
        session = self.client.session
        session["user_timezone"] = "Europe/Kyiv"
        session.save()

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get("user_timezone"), "Europe/Kyiv")

    def test_invalid_timezone_is_discarded(self):
        session = self.client.session
        session["user_timezone"] = "Not/AZone"
        session.save()

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get("user_timezone"))
