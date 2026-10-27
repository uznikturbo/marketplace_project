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


class InfoPageTests(BaseTestCase):
    PAGES = [
        ("about", "Про компанію"),
        ("careers", "Вакансії"),
        ("news", "Новини"),
        ("contacts", "Контакти"),
        ("how_to_order", "Як зробити замовлення"),
        ("delivery", "Доставка і оплата"),
        ("warranty", "Гарантія і повернення"),
        ("service_centers", "Сервісні центри"),
        ("become_a_seller", "Стати продавцем"),
        ("advertising", "Реклама на сайті"),
        ("affiliate", "Affiliate програма"),
        ("support", "Чат підтримки"),
    ]

    def test_info_pages_render(self):
        for name, title in self.PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, title)
                self.assertNotContains(response, "{'title'")

    def test_unknown_info_page_returns_404(self):
        response = self.client.get("/unknown-page/")

        self.assertEqual(response.status_code, 404)

    def test_header_and_footer_links_resolve(self):
        response = self.client.get(reverse("home"))

        for name, _ in self.PAGES:
            self.assertContains(response, f'href="{reverse(name)}"')

        for name in ("promotions", "new_arrivals", "top_sales"):
            self.assertContains(response, f'href="{reverse(name)}"')
