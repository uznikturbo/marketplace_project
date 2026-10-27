"""End-to-end UI tests driven by Playwright (Firefox).

The tests start a real Django live server against the test database and drive
a headless Firefox browser, so they cover the rendered HTML, the inline CSS
and the inline JavaScript together.

Requirements:
    pip install -r requirements-dev.txt
    python -m playwright install firefox

Run only the UI suite:
    python manage.py test tests.test_ui

If Playwright (or its Firefox build) is missing, the whole suite is skipped.
Set UI_TESTS_REQUIRED=1 to turn that skip into a hard failure (used in CI).
"""

import os
import re
import unittest

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.cache import cache
from django.test import override_settings, tag
from django.urls import reverse

from catalog.models import Product

from .base import (
    FAST_PASSWORD_HASHERS,
    LOCMEM_CACHE,
    make_category,
    make_product,
    make_user,
    make_vendor,
)

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:  # pragma: no cover - exercised only without the dev extra
    expect = None
    sync_playwright = None

UI_TESTS_REQUIRED = os.environ.get("UI_TESTS_REQUIRED") == "1"


@override_settings(CACHES=LOCMEM_CACHE, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class UITestCase(StaticLiveServerTestCase):
    """Base class: live server + one isolated Firefox context per test."""

    @classmethod
    def setUpClass(cls):
        if sync_playwright is None:
            message = "playwright is not installed (pip install -r requirements-dev.txt)"
            if UI_TESTS_REQUIRED:
                raise RuntimeError(message)
            raise unittest.SkipTest(message)

        # Playwright's sync API keeps an event loop in the current thread, which
        # trips Django's async-safety guard on every ORM call (including the
        # per-test database flush).  The flag is scoped to this test class.
        cls._previous_async_unsafe = os.environ.get("DJANGO_ALLOW_ASYNC_UNSAFE")
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "1"

        try:
            cls.playwright = sync_playwright().start()
            cls.browser = cls.playwright.firefox.launch(headless=True)
        except Exception as exc:  # pragma: no cover - depends on local setup
            cls._stop_browser()
            cls._restore_async_unsafe()
            message = f"cannot launch Playwright Firefox: {exc}"
            if UI_TESTS_REQUIRED:
                raise
            raise unittest.SkipTest(message) from exc

        try:
            super().setUpClass()
        except Exception:
            cls._stop_browser()
            cls._restore_async_unsafe()
            raise

    @classmethod
    def tearDownClass(cls):
        cls._stop_browser()
        super().tearDownClass()
        cls._restore_async_unsafe()

    @classmethod
    def _restore_async_unsafe(cls):
        previous = getattr(cls, "_previous_async_unsafe", None)
        if previous is None:
            os.environ.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)
        else:
            os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = previous

    @classmethod
    def _stop_browser(cls):
        browser = getattr(cls, "browser", None)
        if browser is not None:
            browser.close()
            cls.browser = None
        playwright = getattr(cls, "playwright", None)
        if playwright is not None:
            playwright.stop()
            cls.playwright = None

    def setUp(self):
        super().setUp()
        cache.clear()
        self.context = self.browser.new_context(
            base_url=self.live_server_url,
            viewport={"width": 1440, "height": 1000},
            locale="uk-UA",
        )
        # Tests must not depend on external fonts or placeholder images.
        self.context.route("**/*", self._handle_route)
        self.page = self.context.new_page()
        self.page.set_default_timeout(10_000)

    def tearDown(self):
        self.context.close()
        cache.clear()
        super().tearDown()

    def _handle_route(self, route):
        url = route.request.url
        if url.startswith(self.live_server_url) or url.startswith("data:"):
            route.continue_()
        else:
            route.abort()

    def login(self, user):
        """Attach an authenticated Django session to the browser context."""
        self.client.force_login(user)
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME]
        self.context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": cookie.value,
                    "url": self.live_server_url,
                }
            ]
        )


@tag("ui")
class HomePageUITests(UITestCase):
    def test_home_renders_categories_and_latest_products(self):
        root = make_category("Електроніка")
        child = make_category("Ноутбуки", parent=root)
        make_product(category=child, name="Ноутбук Test")

        self.page.goto("/")

        expect(self.page.locator(".categories-grid .cat-card")).to_have_count(1)
        expect(self.page.locator(".categories-grid")).to_contain_text("Електроніка")
        expect(self.page.locator(".categories-grid")).not_to_contain_text("Ноутбуки")
        expect(self.page.locator(".products-scroll .product-card")).to_have_count(1)
        expect(self.page.locator(".products-scroll")).to_contain_text("Ноутбук Test")

    def test_category_card_opens_filtered_catalog(self):
        root = make_category("Електроніка")
        child = make_category("Ноутбуки", parent=root)
        make_product(category=child, name="Ноутбук Alpha")
        make_product(category=make_category("Одяг"), name="Футболка Beta")

        self.page.goto("/")
        self.page.locator(".categories-grid .cat-card", has_text="Електроніка").click()

        expect(self.page).to_have_url(re.compile(rf"\?category={root.pk}$"))
        expect(self.page.locator(".products-grid .product-card")).to_have_count(1)
        expect(self.page.locator(".products-grid")).to_contain_text("Ноутбук Alpha")
        expect(self.page.locator(".products-grid")).not_to_contain_text("Футболка Beta")


@tag("ui")
class CatalogUITests(UITestCase):
    def test_search_filters_products(self):
        make_product(name="Ноутбук Alpha")
        make_product(name="Футболка Beta")

        self.page.goto("/catalog/")
        self.page.locator('.search-bar input[name="q"]').fill("Alpha")
        self.page.locator('.search-bar button[type="submit"]').click()

        expect(self.page).to_have_url(re.compile(r"\?q=Alpha$"))
        expect(self.page.locator(".products-grid")).to_contain_text("Ноутбук Alpha")
        expect(self.page.locator(".products-grid")).not_to_contain_text("Футболка Beta")

    def test_product_card_opens_detail_page(self):
        product = make_product(name="Ноутбук Detail")

        self.page.goto("/catalog/")
        self.page.locator(".product-card", has_text="Ноутбук Detail").click()

        expect(self.page).to_have_url(re.compile(rf"/catalog/{product.pk}/detail/$"))
        expect(self.page.locator("h1").first).to_contain_text("Ноутбук Detail")


@tag("ui")
class CartUITests(UITestCase):
    def test_add_to_cart_and_remove_item(self):
        product = make_product(name="Кошик Тест", quantity=5)

        self.page.goto(reverse("product_detail", args=[product.pk]))
        self.page.locator('form[action*="/cart/add/"] button[type="submit"]').click()
        expect(self.page.locator(".messages")).to_contain_text("додано до кошика")

        self.page.goto("/catalog/cart/")
        expect(self.page.locator(".item-name")).to_have_text("Кошик Тест")

        self.page.locator("button.btn-remove").click()
        expect(self.page.locator(".empty-state")).to_contain_text("Ваш кошик порожній")


@tag("ui")
class AuthUITests(UITestCase):
    def test_login_with_valid_credentials(self):
        user = make_user(password="StrongPass123!")

        self.page.goto("/registration/login/")
        self.page.fill("#id_username", user.number)
        self.page.fill("#id_password", "StrongPass123!")
        self.page.click("button.auth-btn")

        expect(self.page).to_have_url(re.compile(r"/$"))
        expect(self.page.locator(".messages")).to_contain_text("Успішний вхід!")

    def test_login_with_invalid_credentials_shows_error(self):
        user = make_user(password="StrongPass123!")

        self.page.goto("/registration/login/")
        self.page.fill("#id_username", user.number)
        self.page.fill("#id_password", "wrong-password")
        self.page.click("button.auth-btn")

        expect(self.page.locator(".messages")).to_contain_text(
            "Помилка входу. Перевірте введені дані."
        )
        expect(self.page).to_have_url(re.compile(r"/registration/login/$"))


@tag("ui")
class ProfileUITests(UITestCase):
    def test_profile_navigation_between_sections(self):
        user = make_user()

        self.login(user)
        self.page.goto("/users/profile/")

        expect(self.page.locator(".profile-nav")).to_be_visible()
        self.page.locator(".profile-nav a", has_text="Мої замовлення").click()
        expect(self.page).to_have_url(re.compile(r"/users/profile/orders/$"))
        expect(self.page.locator(".profile-nav a.active")).to_contain_text(
            "Мої замовлення"
        )

        self.page.locator(".profile-nav a", has_text="Список бажань").click()
        expect(self.page).to_have_url(re.compile(r"/users/profile/wishlist/$"))
        expect(self.page.locator(".profile-nav a.active")).to_contain_text(
            "Список бажань"
        )

    def test_vendor_sidebar_links_and_active_state(self):
        vendor = make_vendor()

        self.login(vendor)
        self.page.goto("/vendors/")

        expect(self.page.locator(".vendor-sidebar")).to_be_visible()
        expect(self.page.locator(".vendor-nav a.active")).to_contain_text("Мої товари")

        self.page.locator(".vendor-nav a", has_text="Замовлення").click()
        expect(self.page).to_have_url(re.compile(r"/vendors/orders/$"))
        expect(self.page.locator(".vendor-nav a.active")).to_contain_text("Замовлення")

        self.page.locator(".vendor-nav a", has_text="Повернутись у профіль").click()
        expect(self.page).to_have_url(re.compile(r"/users/profile/$"))
        expect(self.page.locator(".profile-nav a.active")).to_contain_text(
            "Особисті дані"
        )


@tag("ui")
class WishlistUITests(UITestCase):
    def test_favorite_toggle_from_home_adds_to_wishlist(self):
        make_product(name="Обране Тест")

        self.page.goto("/")
        card = self.page.locator(".product-card", has_text="Обране Тест")
        button = card.locator("button.card-wishlist")
        button.click()

        expect(button).to_have_class(re.compile(r"\bactive\b"))
        expect(button.locator("svg")).to_have_attribute("fill", "var(--red)")

        self.page.goto("/catalog/wishlist")
        expect(self.page.locator(".wishlist-card")).to_contain_text("Обране Тест")


@tag("ui")
class VendorProductFormUITests(UITestCase):
    def test_create_product_with_dynamic_properties_and_image(self):
        vendor = make_vendor()
        category = make_category("Ноутбуки")

        self.login(vendor)
        self.page.goto("/vendors/create_product/")

        self.page.fill("#id_name", "Новий ноутбук")
        self.page.fill("#id_description", "Опис тестового товару")
        self.page.fill("#id_price", "1500.00")
        self.page.fill("#id_quantity", "3")
        self.page.select_option("#id_category", label=category.name)

        expect(self.page.locator("#dynamic-properties-container .property-row")).to_have_count(1)
        self.page.click("#add-property-btn")
        expect(self.page.locator("#dynamic-properties-container .property-row")).to_have_count(2)

        row = self.page.locator("#dynamic-properties-container .property-row").last
        row.locator(".prop-key").fill("Колір")
        row.locator(".prop-value").fill("Чорний")
        self.page.locator('input[name$="-image_url"]').first.fill(
            "https://example.com/laptop.jpg"
        )

        self.page.click("button.btn-save")

        expect(self.page).to_have_url(re.compile(r"/vendors/$"))
        expect(self.page.locator(".vendor-table")).to_contain_text("Новий ноутбук")

        product = Product.objects.get(name="Новий ноутбук")
        self.assertEqual(product.properties, {"Колір": "Чорний"})
        self.assertEqual(product.images.count(), 1)
        self.assertEqual(product.user, vendor)

    def test_edit_product_prefills_dynamic_properties(self):
        vendor = make_vendor()
        product = make_product(
            vendor=vendor,
            name="Ноутбук Edit",
            properties={"Колір": "Чорний"},
        )

        self.login(vendor)
        self.page.goto(reverse("update_product", args=[product.pk]))

        expect(self.page.locator("#dynamic-properties-container .property-row")).to_have_count(1)
        expect(self.page.locator(".prop-key").first).to_have_value("Колір")
        expect(self.page.locator(".prop-value").first).to_have_value("Чорний")
