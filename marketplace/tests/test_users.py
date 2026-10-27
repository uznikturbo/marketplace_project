import json
from unittest.mock import patch

from django.core.cache import cache
from django.urls import reverse

from catalog.models import Favorite

from .base import BaseTestCase, make_order, make_product, make_user


class ProfileTests(BaseTestCase):
    def test_profile_requires_login(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_profile_renders(self):
        self.client.force_login(make_user())

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)

    def test_profile_update_saves_fields(self):
        user = make_user()
        self.client.force_login(user)

        response = self.client.post(
            reverse("profile"),
            {
                "first_name": "Petro",
                "last_name": "Shevchenko",
                "number": user.number,
                "email": "petro@example.com",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Petro")
        self.assertEqual(user.email, "petro@example.com")

    def test_changing_number_unconfirms_user(self):
        user = make_user(confirmed=True)
        self.client.force_login(user)

        self.client.post(
            reverse("profile"),
            {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "number": "0509998877",
                "email": user.email,
            },
        )

        user.refresh_from_db()
        self.assertEqual(user.number, "+380509998877")
        self.assertFalse(user.confirmed)

    def test_duplicate_email_is_reported_by_form(self):
        make_user(email="taken@example.com")
        user = make_user()
        self.client.force_login(user)

        response = self.client.post(
            reverse("profile"),
            {
                "first_name": "Ivan",
                "last_name": "Petrenko",
                "number": user.number,
                "email": "TAKEN@example.com",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        user.refresh_from_db()
        self.assertNotEqual(user.email, "taken@example.com")

    def test_profile_orders_show_only_own_orders(self):
        user = make_user()
        mine = make_order(user=user)
        foreign = make_order(user=make_user())
        self.client.force_login(user)

        response = self.client.get(reverse("profile_orders"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"Замовлення #{mine.id}")
        self.assertNotContains(response, f"Замовлення #{foreign.id}")

    def test_profile_wishlist_shows_favorites(self):
        user = make_user()
        product = make_product(name="Favourite item")
        Favorite.objects.create(user=user, product=product)
        self.client.force_login(user)

        response = self.client.get(reverse("profile_wishlist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, product.name)


class SmsVerificationTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.user = make_user(confirmed=False)
        self.client.force_login(self.user)
        self.code_key = f"sms_code_{self.user.number}"
        self.lock_key = f"sms_lock_{self.user.number}"
        self.attempts_key = f"sms_attempts_{self.user.number}"

    def _send(self):
        return self.client.post(reverse("send_verification_sms"))

    def _verify(self, code):
        return self.client.post(
            reverse("verify_sms_code"),
            data=json.dumps({"code": code}),
            content_type="application/json",
        )

    def test_send_requires_login(self):
        self.client.logout()

        response = self._send()

        self.assertEqual(response.status_code, 302)

    def test_send_rejected_for_confirmed_user(self):
        self.user.confirmed = True
        self.user.save()

        response = self._send()

        self.assertEqual(response.status_code, 400)

    @patch("users.views.send_sms_conf_task.delay")
    def test_send_stores_code_and_schedules_task(self, mock_delay):
        response = self._send()

        self.assertEqual(response.status_code, 200)
        code = cache.get(self.code_key)
        self.assertIsNotNone(code)
        self.assertEqual(len(code), 6)
        mock_delay.assert_called_once_with(self.user.number, code)
        self.assertTrue(cache.get(self.lock_key))

    @patch("users.views.send_sms_conf_task.delay")
    def test_second_send_is_rate_limited(self, mock_delay):
        self._send()

        response = self._send()

        self.assertEqual(response.status_code, 429)
        self.assertEqual(mock_delay.call_count, 1)

    @patch("users.views.send_sms_conf_task.delay", side_effect=Exception("broker down"))
    def test_broker_failure_returns_503_and_clears_state(self, mock_delay):
        response = self._send()

        self.assertEqual(response.status_code, 503)
        self.assertIsNone(cache.get(self.code_key))
        self.assertIsNone(cache.get(self.lock_key))

    def test_verify_rejects_invalid_json(self):
        response = self.client.post(
            reverse("verify_sms_code"),
            data="not-json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_verify_rejects_empty_code(self):
        response = self._verify("")

        self.assertEqual(response.status_code, 400)

    def test_verify_without_saved_code_returns_400(self):
        response = self._verify("123456")

        self.assertEqual(response.status_code, 400)

    def test_verify_wrong_code_increments_attempts(self):
        cache.set(self.code_key, "123456", timeout=300)

        response = self._verify("000000")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(cache.get(self.attempts_key), 1)
        self.user.refresh_from_db()
        self.assertFalse(self.user.confirmed)

    def test_verify_blocks_after_too_many_attempts(self):
        cache.set(self.code_key, "123456", timeout=300)
        for _ in range(5):
            self._verify("000000")

        response = self._verify("123456")

        self.assertEqual(response.status_code, 429)
        self.user.refresh_from_db()
        self.assertFalse(self.user.confirmed)

    def test_verify_correct_code_confirms_user(self):
        cache.set(self.code_key, "123456", timeout=300)
        cache.set(self.attempts_key, 2, timeout=300)

        response = self._verify("123456")

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.confirmed)
        self.assertIsNone(cache.get(self.code_key))
        self.assertIsNone(cache.get(self.attempts_key))

    def test_verify_rejected_for_confirmed_user(self):
        self.user.confirmed = True
        self.user.save()
        cache.set(self.code_key, "123456", timeout=300)

        response = self._verify("123456")

        self.assertEqual(response.status_code, 400)


class ProfilePaginationTests(BaseTestCase):
    def test_profile_orders_are_paginated(self):
        user = make_user()
        for _ in range(11):
            make_order(user=user)
        self.client.force_login(user)

        first = self.client.get(reverse("profile_orders"))
        second = self.client.get(reverse("profile_orders"), {"page": 2})

        self.assertEqual(len(first.context["orders"]), 10)
        self.assertEqual(first.context["page_obj"].paginator.count, 11)
        self.assertEqual(len(second.context["orders"]), 1)
        self.assertContains(first, 'class="pagination"')

    def test_profile_wishlist_is_paginated(self):
        user = make_user()
        for i in range(13):
            Favorite.objects.create(user=user, product=make_product(name=f"Fav {i:02d}"))
        self.client.force_login(user)

        first = self.client.get(reverse("profile_wishlist"))
        second = self.client.get(reverse("profile_wishlist"), {"page": 2})

        self.assertEqual(len(first.context["products"]), 12)
        self.assertEqual(first.context["page_obj"].paginator.count, 13)
        self.assertEqual(len(second.context["products"]), 1)
        self.assertContains(first, 'class="pagination"')
