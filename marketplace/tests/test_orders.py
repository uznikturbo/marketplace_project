import base64
import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Cart, ProductDiscount
from orders.models import (
    Order,
    OrderItem,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)

from .base import (
    BaseTestCase,
    checkout_payload,
    make_order,
    make_product,
    make_user,
)

LIQPAY_SETTINGS = {
    "LIQPAY_PUBLIC_KEY": "sandbox_public",
    "LIQPAY_PRIVATE_KEY": "sandbox_private",
}


def liqpay_payload(order_id, status="success", private_key="sandbox_private", **extra):
    data = {
        "order_id": order_id,
        "status": status,
        "transaction_id": "tx-123",
        "amount": "100.00",
        "currency": "UAH",
    }
    data.update(extra)
    encoded = base64.b64encode(json.dumps(data).encode("utf-8")).decode("utf-8")
    sign_string = private_key + encoded + private_key
    signature = base64.b64encode(
        hashlib.sha1(sign_string.encode("utf-8")).digest()
    ).decode("utf-8")
    return {"data": encoded, "signature": signature}


@override_settings(**LIQPAY_SETTINGS)
class CheckoutTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product(price=Decimal("100.00"), quantity=10)

    def _add_to_cart(self, quantity=2):
        return self.client.post(
            reverse("cart_add", args=[self.product.pk]), {"quantity": quantity}
        )

    def test_empty_cart_redirects_to_catalog(self):
        response = self.client.get(reverse("checkout"))

        self.assertRedirects(response, reverse("catalog"))

    def test_get_with_cart_renders_form(self):
        self._add_to_cart()

        response = self.client.get(reverse("checkout"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_postpaid_order_is_created(self):
        self._add_to_cart(quantity=2)

        response = self.client.post(
            reverse("checkout"), checkout_payload()
        )

        order = Order.objects.get()
        self.assertRedirects(response, reverse("order_success", args=[order.id]))
        self.assertEqual(order.total_products, Decimal("200.00"))
        self.assertEqual(order.postpaid_fee, Decimal("24.00"))
        self.assertEqual(order.total_amount, Decimal("224.00"))
        self.assertEqual(order.status, OrderStatus.NEW)
        self.assertEqual(order.payment_status, PaymentStatus.PENDING)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.get().quantity, 2)

    def test_stock_is_decremented_and_cart_cleared(self):
        self._add_to_cart(quantity=3)

        self.client.post(reverse("checkout"), checkout_payload())

        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 7)
        cart = Cart.objects.get(session_key=self.client.session["cart_session_key"])
        self.assertEqual(cart.items.count(), 0)

    def test_order_item_uses_discounted_price(self):
        now = timezone.now()
        ProductDiscount.objects.create(
            product=self.product,
            value=50,
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=1),
        )
        self._add_to_cart(quantity=1)

        self.client.post(reverse("checkout"), checkout_payload())

        item = OrderItem.objects.get()
        self.assertEqual(item.price, Decimal("50.00"))

    def test_insufficient_stock_rolls_back(self):
        self._add_to_cart(quantity=1)
        self.product.quantity = 0
        self.product.save()

        response = self.client.post(reverse("checkout"), checkout_payload())

        self.assertRedirects(response, reverse("checkout"))
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderItem.objects.count(), 0)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 0)

    def test_unavailable_product_rolls_back(self):
        self._add_to_cart(quantity=1)
        self.product.is_available = False
        self.product.save()

        response = self.client.post(reverse("checkout"), checkout_payload())

        self.assertRedirects(response, reverse("checkout"))
        self.assertEqual(Order.objects.count(), 0)

    def test_liqpay_is_rejected_when_not_configured(self):
        self._add_to_cart(quantity=1)

        with override_settings(LIQPAY_PUBLIC_KEY=None, LIQPAY_PRIVATE_KEY=None):
            response = self.client.post(
                reverse("checkout"),
                checkout_payload(payment_method=PaymentMethod.LIQPAY),
            )

        self.assertRedirects(response, reverse("checkout"))
        self.assertEqual(Order.objects.count(), 0)

    def test_liqpay_order_renders_signed_redirect(self):
        self._add_to_cart(quantity=1)

        response = self.client.post(
            reverse("checkout"), checkout_payload(payment_method=PaymentMethod.LIQPAY)
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "orders/liqpay_redirect.html")
        data = response.context["data"]
        signature = response.context["signature"]
        expected = base64.b64encode(
            hashlib.sha1(
                (
                    LIQPAY_SETTINGS["LIQPAY_PRIVATE_KEY"]
                    + data
                    + LIQPAY_SETTINGS["LIQPAY_PRIVATE_KEY"]
                ).encode("utf-8")
            ).digest()
        ).decode("utf-8")
        self.assertEqual(signature, expected)
        self.assertEqual(Order.objects.get().payment_method, PaymentMethod.LIQPAY)

    def test_guest_order_is_stored_in_session(self):
        self._add_to_cart(quantity=1)

        self.client.post(reverse("checkout"), checkout_payload())

        order = Order.objects.get()
        self.assertIsNone(order.user)
        self.assertIn(order.id, self.client.session["guest_order_ids"])

    def test_authenticated_order_is_linked_to_user(self):
        user = make_user()
        self.client.force_login(user)
        self._add_to_cart(quantity=1)

        self.client.post(
            reverse("checkout"),
            checkout_payload(first_name="Petro", city_ref="city-ref"),
        )

        order = Order.objects.get()
        self.assertEqual(order.user, user)
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Petro")
        self.assertEqual(user.default_city_ref, "city-ref")

    def test_invalid_form_does_not_create_order(self):
        self._add_to_cart(quantity=1)
        payload = checkout_payload()
        payload.pop("first_name")

        response = self.client.post(reverse("checkout"), payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)


@override_settings(**LIQPAY_SETTINGS)
class OrderSuccessTests(BaseTestCase):
    def test_owner_can_view_order(self):
        user = make_user()
        order = make_order(user=user)
        self.client.force_login(user)

        response = self.client.get(reverse("order_success", args=[order.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(order.id))

    def test_other_user_is_redirected_home(self):
        order = make_order(user=make_user())
        self.client.force_login(make_user())

        response = self.client.get(reverse("order_success", args=[order.id]))

        self.assertRedirects(response, reverse("home"))

    def test_guest_sees_own_order_from_session(self):
        order = make_order()
        session = self.client.session
        session["guest_order_ids"] = [order.id]
        session.save()

        response = self.client.get(reverse("order_success", args=[order.id]))

        self.assertEqual(response.status_code, 200)

    def test_guest_cannot_view_order_not_in_session(self):
        order = make_order()

        response = self.client.get(reverse("order_success", args=[order.id]))

        self.assertRedirects(response, reverse("home"))

    def test_anonymous_cannot_view_user_order(self):
        order = make_order(user=make_user())
        session = self.client.session
        session["guest_order_ids"] = [order.id]
        session.save()

        response = self.client.get(reverse("order_success", args=[order.id]))

        self.assertRedirects(response, reverse("home"))

    def test_pending_liqpay_order_gets_payment_payload(self):
        order = make_order(
            user=make_user(), payment_method=PaymentMethod.LIQPAY
        )
        self.client.force_login(order.user)

        response = self.client.get(reverse("order_success", args=[order.id]))

        self.assertIsNotNone(response.context["liqpay_data"])
        self.assertIsNotNone(response.context["liqpay_signature"])

    def test_paid_order_does_not_get_payment_payload(self):
        order = make_order(
            user=make_user(),
            payment_method=PaymentMethod.LIQPAY,
            payment_status=PaymentStatus.PAID,
        )
        self.client.force_login(order.user)

        response = self.client.get(reverse("order_success", args=[order.id]))

        self.assertIsNone(response.context["liqpay_data"])


@override_settings(**LIQPAY_SETTINGS)
class OrderPayTests(BaseTestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        order = make_order(payment_method=PaymentMethod.LIQPAY)

        response = self.client.get(reverse("order_pay", args=[order.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_other_users_order_returns_404(self):
        order = make_order(user=make_user(), payment_method=PaymentMethod.LIQPAY)
        self.client.force_login(make_user())

        response = self.client.get(reverse("order_pay", args=[order.pk]))

        self.assertEqual(response.status_code, 404)

    def test_non_liqpay_order_is_redirected(self):
        user = make_user()
        order = make_order(user=user, payment_method=PaymentMethod.POSTPAID)
        self.client.force_login(user)

        response = self.client.get(reverse("order_pay", args=[order.pk]))

        self.assertRedirects(response, reverse("profile_orders"))

    def test_paid_order_is_redirected(self):
        user = make_user()
        order = make_order(
            user=user,
            payment_method=PaymentMethod.LIQPAY,
            payment_status=PaymentStatus.PAID,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("order_pay", args=[order.pk]))

        self.assertRedirects(response, reverse("profile_orders"))

    def test_unconfigured_liqpay_is_redirected(self):
        user = make_user()
        order = make_order(user=user, payment_method=PaymentMethod.LIQPAY)
        self.client.force_login(user)

        with override_settings(LIQPAY_PUBLIC_KEY=None, LIQPAY_PRIVATE_KEY=None):
            response = self.client.get(reverse("order_pay", args=[order.pk]))

        self.assertRedirects(response, reverse("profile_orders"))

    def test_configured_liqpay_renders_redirect(self):
        user = make_user()
        order = make_order(user=user, payment_method=PaymentMethod.LIQPAY)
        self.client.force_login(user)

        response = self.client.get(reverse("order_pay", args=[order.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "orders/liqpay_redirect.html")
        self.assertIsNotNone(response.context["signature"])


@override_settings(**LIQPAY_SETTINGS)
class LiqPayCallbackTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.order = make_order(
            payment_method=PaymentMethod.LIQPAY,
            total_amount=Decimal("100.00"),
        )
        self.url = reverse("liqpay_callback")

    def test_get_is_not_allowed(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)

    def test_missing_data_is_rejected(self):
        response = self.client.post(self.url, {})

        self.assertEqual(response.status_code, 400)

    def test_unconfigured_private_key_returns_503(self):
        with override_settings(LIQPAY_PRIVATE_KEY=""):
            response = self.client.post(self.url, liqpay_payload(self.order.id))

        self.assertEqual(response.status_code, 503)

    def test_invalid_signature_is_rejected(self):
        payload = liqpay_payload(self.order.id)
        payload["signature"] = "invalid"

        response = self.client.post(self.url, payload)

        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PENDING)

    def test_malformed_data_is_rejected(self):
        data = "not-base64-json"
        private_key = LIQPAY_SETTINGS["LIQPAY_PRIVATE_KEY"]
        signature = base64.b64encode(
            hashlib.sha1(
                (private_key + data + private_key).encode("utf-8")
            ).digest()
        ).decode("utf-8")

        response = self.client.post(self.url, {"data": data, "signature": signature})

        self.assertEqual(response.status_code, 400)

    def test_missing_order_id_is_rejected(self):
        payload = liqpay_payload(None)
        response = self.client.post(self.url, payload)

        self.assertEqual(response.status_code, 400)

    def test_unknown_order_returns_404(self):
        response = self.client.post(self.url, liqpay_payload(999999))

        self.assertEqual(response.status_code, 404)

    def test_success_marks_order_as_paid(self):
        response = self.client.post(self.url, liqpay_payload(self.order.id))

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)
        self.assertEqual(self.order.status, OrderStatus.PROCESSING)
        self.assertEqual(self.order.payment_id, "tx-123")

    def test_order_id_with_timestamp_suffix_is_supported(self):
        order_id = f"{self.order.id}_1712345678"

        response = self.client.post(self.url, liqpay_payload(order_id))

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)

    @override_settings(LIQPAY_SANDBOX=True)
    def test_sandbox_status_marks_order_as_paid_when_enabled(self):
        self.client.post(self.url, liqpay_payload(self.order.id, status="sandbox"))

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)

    def test_sandbox_status_is_rejected_by_default(self):
        response = self.client.post(
            self.url, liqpay_payload(self.order.id, status="sandbox")
        )

        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PENDING)

    def test_wrong_amount_is_rejected(self):
        response = self.client.post(
            self.url, liqpay_payload(self.order.id, amount="1.00")
        )

        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PENDING)

    def test_wrong_currency_is_rejected(self):
        response = self.client.post(
            self.url, liqpay_payload(self.order.id, currency="USD")
        )

        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PENDING)

    def test_non_liqpay_order_is_rejected(self):
        order = make_order(payment_method=PaymentMethod.POSTPAID)

        response = self.client.post(self.url, liqpay_payload(order.id))

        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, PaymentStatus.PENDING)

    def test_cancelled_order_is_not_marked_as_paid(self):
        self.order.status = OrderStatus.CANCELLED
        self.order.save(update_fields=["status"])

        response = self.client.post(self.url, liqpay_payload(self.order.id))

        self.assertEqual(response.status_code, 409)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PENDING)

    def test_failure_marks_order_as_failed(self):
        self.client.post(self.url, liqpay_payload(self.order.id, status="failure"))

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.FAILED)

    def test_failure_does_not_overwrite_paid_order(self):
        self.order.payment_status = PaymentStatus.PAID
        self.order.save()

        self.client.post(self.url, liqpay_payload(self.order.id, status="failure"))

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)

    def test_unknown_status_keeps_order_unchanged(self):
        self.client.post(self.url, liqpay_payload(self.order.id, status="processing"))

        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PENDING)


class NovaPoshtaTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_cities_without_api_key_return_503(self):
        with override_settings(NOVAPOST_API=None):
            response = self.client.get(reverse("np_cities"), {"q": "Kyiv"})

        self.assertEqual(response.status_code, 503)

    @override_settings(NOVAPOST_API="test-key")
    @patch("orders.novaposhta.requests.post")
    def test_cities_are_proxied(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "data": [{"City": "Kyiv"}]}
        mock_post.return_value = mock_response

        response = self.client.get(reverse("np_cities"), {"q": "Kyiv"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["City"], "Kyiv")
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args.kwargs["timeout"], 10)

    @override_settings(NOVAPOST_API="test-key")
    @patch("orders.novaposhta.requests.post")
    def test_cities_are_cached(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "data": [{"City": "Kyiv"}]}
        mock_post.return_value = mock_response

        self.client.get(reverse("np_cities"), {"q": "Kyiv"})
        response = self.client.get(reverse("np_cities"), {"q": "Kyiv"})

        self.assertEqual(response.status_code, 200)
        mock_post.assert_called_once()

    @override_settings(NOVAPOST_API="test-key")
    @patch("orders.novaposhta.requests.post")
    def test_short_city_query_does_not_call_api(self, mock_post):
        response = self.client.get(reverse("np_cities"), {"q": "K"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], [])
        mock_post.assert_not_called()

    @override_settings(NOVAPOST_API="test-key")
    @patch("orders.novaposhta.requests.post", side_effect=requests.RequestException("boom"))
    def test_cities_api_failure_returns_502(self, mock_post):
        response = self.client.get(reverse("np_cities"), {"q": "Kyiv"})

        self.assertEqual(response.status_code, 502)

    @override_settings(NOVAPOST_API="test-key")
    @patch("orders.novaposhta.time.sleep")
    @patch("orders.novaposhta.requests.post")
    def test_cities_rate_limit_is_retried_then_returned(self, mock_post, mock_sleep):
        limited = MagicMock(status_code=429, headers={"Retry-After": "0"})
        mock_post.return_value = limited

        response = self.client.get(reverse("np_cities"), {"q": "Kyiv"})

        self.assertEqual(response.status_code, 429)
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once()

    @override_settings(NOVAPOST_API="test-key")
    @patch("orders.novaposhta.time.sleep")
    @patch("orders.novaposhta.requests.post")
    def test_cities_rate_limit_can_recover_on_retry(self, mock_post, mock_sleep):
        limited = MagicMock(status_code=429, headers={"Retry-After": "0"})
        success = MagicMock()
        success.json.return_value = {"success": True, "data": [{"City": "Kyiv"}]}
        mock_post.side_effect = [limited, success]

        response = self.client.get(reverse("np_cities"), {"q": "Kyiv"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once()

    def test_warehouses_without_api_key_return_503(self):
        with override_settings(NOVAPOST_API=None):
            response = self.client.get(reverse("np_warehouses"), {"city_ref": "ref"})

        self.assertEqual(response.status_code, 503)

    @override_settings(NOVAPOST_API="test-key")
    def test_warehouses_require_city_ref(self):
        response = self.client.get(reverse("np_warehouses"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["success"])

    @override_settings(NOVAPOST_API="test-key")
    @patch("orders.novaposhta.requests.post")
    def test_warehouses_are_proxied(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "data": [{"Number": "1"}]}
        mock_post.return_value = mock_response

        response = self.client.get(reverse("np_warehouses"), {"city_ref": "ref"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["Number"], "1")

    @override_settings(NOVAPOST_API="test-key")
    @patch("orders.novaposhta.requests.post")
    def test_warehouses_are_cached(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True, "data": [{"Number": "1"}]}
        mock_post.return_value = mock_response

        self.client.get(reverse("np_warehouses"), {"city_ref": "ref"})
        response = self.client.get(reverse("np_warehouses"), {"city_ref": "ref"})

        self.assertEqual(response.status_code, 200)
        mock_post.assert_called_once()
