from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from catalog.models import Product, ProductDiscount
from orders.models import (
    OrderItem,
    OrderItemStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)

from .base import (
    BaseTestCase,
    make_category,
    make_order,
    make_product,
    make_user,
    make_vendor,
)


class VendorAccessTests(BaseTestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("vendor_view"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_non_vendor_is_redirected_to_profile(self):
        self.client.force_login(make_user())

        response = self.client.get(reverse("vendor_view"))

        self.assertRedirects(response, reverse("profile"))

    def test_vendor_can_open_dashboard(self):
        self.client.force_login(make_vendor())

        response = self.client.get(reverse("vendor_view"))

        self.assertEqual(response.status_code, 200)

    def test_vendor_sees_only_own_products(self):
        vendor = make_vendor()
        own = make_product(vendor=vendor, name="Own product")
        foreign = make_product(name="Foreign product")
        self.client.force_login(vendor)

        response = self.client.get(reverse("vendor_view"))

        self.assertContains(response, own.name)
        self.assertNotContains(response, foreign.name)


class VendorProductTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.vendor = make_vendor()
        self.client.force_login(self.vendor)

    def _formset_data(self, **overrides):
        data = {
            "images-TOTAL_FORMS": "0",
            "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "1000",
        }
        data.update(overrides)
        return data

    def test_create_product(self):
        category = make_category()
        payload = {
            "name": "New product",
            "description": "Brand new",
            "price": "150.00",
            "quantity": 7,
            "category": category.pk,
            "properties": "{}",
        }
        payload.update(self._formset_data())

        response = self.client.post(reverse("create_product"), payload)

        self.assertRedirects(response, reverse("vendor_view"))
        product = Product.objects.get(name="New product")
        self.assertEqual(product.user, self.vendor)
        self.assertEqual(product.price, Decimal("150.00"))
        self.assertEqual(product.quantity, 7)

    def test_create_product_with_image(self):
        category = make_category()
        payload = {
            "name": "Product with image",
            "description": "Has an image",
            "price": "10.00",
            "quantity": 1,
            "category": category.pk,
            "properties": "{}",
        }
        payload.update(
            self._formset_data(
                **{
                    "images-TOTAL_FORMS": "1",
                    "images-0-image_url": "https://example.com/image.jpg",
                }
            )
        )

        self.client.post(reverse("create_product"), payload)

        product = Product.objects.get(name="Product with image")
        self.assertEqual(product.images.count(), 1)

    def test_negative_price_is_rejected(self):
        payload = {
            "name": "Negative price",
            "description": "Invalid",
            "price": "-1.00",
            "quantity": 1,
            "category": make_category().pk,
            "properties": "{}",
        }
        payload.update(self._formset_data())

        response = self.client.post(reverse("create_product"), payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(name="Negative price").exists())

    def test_invalid_product_is_not_created(self):
        payload = {
            "name": "",
            "description": "No name",
            "price": "10.00",
            "quantity": 1,
            "category": make_category().pk,
            "properties": "{}",
        }
        payload.update(self._formset_data())

        response = self.client.post(reverse("create_product"), payload)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(description="No name").exists())

    def test_update_own_product(self):
        product = make_product(vendor=self.vendor, name="Old name")
        payload = {
            "name": "Updated name",
            "description": product.description,
            "price": "99.00",
            "quantity": 3,
            "category": product.category.pk,
            "properties": "{}",
        }
        payload.update(self._formset_data())

        response = self.client.post(
            reverse("update_product", args=[product.pk]), payload
        )

        self.assertRedirects(response, reverse("vendor_view"))
        product.refresh_from_db()
        self.assertEqual(product.name, "Updated name")
        self.assertEqual(product.price, Decimal("99.00"))

    def test_cannot_update_foreign_product(self):
        foreign = make_product(name="Foreign")

        response = self.client.get(reverse("update_product", args=[foreign.pk]))

        self.assertEqual(response.status_code, 404)

    def test_delete_own_product(self):
        product = make_product(vendor=self.vendor)

        response = self.client.post(reverse("delete_product", args=[product.pk]))

        self.assertRedirects(response, reverse("vendor_view"))
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_cannot_delete_foreign_product(self):
        foreign = make_product()

        response = self.client.post(reverse("delete_product", args=[foreign.pk]))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Product.objects.filter(pk=foreign.pk).exists())

    def test_delete_requires_post(self):
        product = make_product(vendor=self.vendor)

        response = self.client.get(reverse("delete_product", args=[product.pk]))

        self.assertEqual(response.status_code, 405)


class VendorDiscountTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.vendor = make_vendor()
        self.product = make_product(vendor=self.vendor)
        self.client.force_login(self.vendor)

    def _payload(self, **overrides):
        now = timezone.now()
        payload = {
            "value": 15,
            "start_at": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            "end_at": (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
        }
        payload.update(overrides)
        return payload

    def test_add_valid_discount(self):
        response = self.client.post(
            reverse("add_discount", args=[self.product.pk]), self._payload()
        )

        self.assertRedirects(response, reverse("vendor_view"))
        discount = ProductDiscount.objects.get(product=self.product)
        self.assertEqual(discount.value, 15)

    def test_discount_above_hundred_is_rejected(self):
        response = self.client.post(
            reverse("add_discount", args=[self.product.pk]),
            self._payload(value=150),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductDiscount.objects.filter(product=self.product).exists())

    def test_end_before_start_is_rejected(self):
        now = timezone.now()
        response = self.client.post(
            reverse("add_discount", args=[self.product.pk]),
            self._payload(
                start_at=(now + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
                end_at=(now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ProductDiscount.objects.filter(product=self.product).exists())

    def test_cannot_add_discount_to_foreign_product(self):
        foreign = make_product()

        response = self.client.get(reverse("add_discount", args=[foreign.pk]))

        self.assertEqual(response.status_code, 404)


class VendorOrderTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.vendor = make_vendor()
        self.product = make_product(vendor=self.vendor, price=Decimal("50.00"))
        self.other_product = make_product(price=Decimal("10.00"))
        self.order = make_order(
            user=make_user(), payment_method=PaymentMethod.POSTPAID
        )
        OrderItem.objects.create(
            order=self.order,
            product=self.product,
            name=self.product.name,
            price=Decimal("50.00"),
            quantity=2,
        )
        self.foreign_order = make_order(user=make_user())
        OrderItem.objects.create(
            order=self.foreign_order,
            product=self.other_product,
            name=self.other_product.name,
            price=Decimal("10.00"),
            quantity=1,
        )
        self.client.force_login(self.vendor)

    def test_vendor_orders_list_contains_only_related_orders(self):
        response = self.client.get(reverse("vendor_orders"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"#{self.order.id}</strong>")
        self.assertNotContains(response, f"#{self.foreign_order.id}</strong>")

    def test_vendor_order_detail_is_available(self):
        response = self.client.get(
            reverse("vendor_order_details", args=[self.order.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertNotContains(response, self.other_product.name)

    def test_vendor_cannot_open_foreign_order(self):
        response = self.client.get(
            reverse("vendor_order_details", args=[self.foreign_order.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_vendor_can_update_order_status(self):
        response = self.client.post(
            reverse("vendor_order_details", args=[self.order.pk]),
            {"status": OrderStatus.SHIPPED},
        )

        self.assertRedirects(
            response, reverse("vendor_order_details", args=[self.order.pk])
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.SHIPPED)

    def test_invalid_status_is_ignored(self):
        response = self.client.post(
            reverse("vendor_order_details", args=[self.order.pk]),
            {"status": "not-a-status"},
        )

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.NEW)


class VendorOrderItemCancellationTests(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.vendor = make_vendor()
        self.other_vendor = make_vendor()
        self.product = make_product(
            vendor=self.vendor, price=Decimal("50.00"), quantity=8
        )
        self.other_product = make_product(
            vendor=self.other_vendor, price=Decimal("10.00"), quantity=5
        )
        self.order = make_order(
            user=make_user(),
            payment_method=PaymentMethod.POSTPAID,
            total_products=Decimal("110.00"),
            total_amount=Decimal("110.00"),
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            product=self.product,
            name=self.product.name,
            price=Decimal("50.00"),
            quantity=2,
        )
        self.other_item = OrderItem.objects.create(
            order=self.order,
            product=self.other_product,
            name=self.other_product.name,
            price=Decimal("10.00"),
            quantity=1,
        )
        self.client.force_login(self.vendor)

    def _cancel_url(self, order=None, item=None):
        return reverse(
            "vendor_cancel_order_item",
            args=[(order or self.order).pk, (item or self.item).pk],
        )

    def test_vendor_cancels_only_selected_item(self):
        response = self.client.post(self._cancel_url(), follow=True)

        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.other_item.refresh_from_db()
        self.order.refresh_from_db()
        self.product.refresh_from_db()

        self.assertEqual(self.item.status, OrderItemStatus.CANCELLED)
        self.assertEqual(self.other_item.status, OrderItemStatus.ACTIVE)
        self.assertEqual(self.order.status, OrderStatus.NEW)
        self.assertEqual(self.product.quantity, 10)
        self.assertEqual(self.order.total_products, Decimal("10.00"))
        self.assertEqual(self.order.postpaid_fee, Decimal("20.20"))
        self.assertEqual(self.order.total_amount, Decimal("30.20"))
        self.assertContains(response, "Скасовано")

    def test_cancelling_last_item_cancels_whole_order(self):
        order = make_order(
            user=make_user(),
            payment_method=PaymentMethod.POSTPAID,
            total_products=Decimal("100.00"),
            total_amount=Decimal("100.00"),
        )
        item = OrderItem.objects.create(
            order=order,
            product=self.product,
            name=self.product.name,
            price=Decimal("50.00"),
            quantity=2,
        )

        response = self.client.post(self._cancel_url(order, item), follow=True)

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(item.status, OrderItemStatus.CANCELLED)
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        self.assertEqual(order.total_products, Decimal("0.00"))
        self.assertEqual(order.total_amount, Decimal("0.00"))

    def test_vendor_cannot_cancel_foreign_item(self):
        response = self.client.post(
            self._cancel_url(self.order, self.other_item)
        )

        self.assertEqual(response.status_code, 404)
        self.other_item.refresh_from_db()
        self.assertEqual(self.other_item.status, OrderItemStatus.ACTIVE)

    def test_vendor_cannot_cancel_item_in_shipped_order(self):
        self.order.status = OrderStatus.SHIPPED
        self.order.save(update_fields=["status"])

        response = self.client.post(self._cancel_url(), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Не можна скасувати товар")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, OrderItemStatus.ACTIVE)

    def test_vendor_cannot_cancel_item_twice(self):
        self.client.post(self._cancel_url())
        response = self.client.post(self._cancel_url(), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "уже скасовано")
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity, 10)

    def test_cancel_endpoint_requires_post(self):
        response = self.client.get(self._cancel_url())

        self.assertEqual(response.status_code, 405)

    def test_cannot_cancel_pending_liqpay_item(self):
        self.order.payment_method = PaymentMethod.LIQPAY
        self.order.payment_status = PaymentStatus.PENDING
        self.order.save(update_fields=["payment_method", "payment_status"])

        response = self.client.post(self._cancel_url(), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "до завершення оплати")
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, OrderItemStatus.ACTIVE)


class VendorPaginationTests(BaseTestCase):
    def test_vendor_products_are_paginated(self):
        vendor = make_vendor()
        for i in range(21):
            make_product(vendor=vendor, name=f"Vendor product {i:02d}")
        self.client.force_login(vendor)

        first = self.client.get(reverse("vendor_view"))
        second = self.client.get(reverse("vendor_view"), {"page": 2})

        self.assertEqual(len(first.context["vendor_products"]), 20)
        self.assertEqual(first.context["page_obj"].paginator.count, 21)
        self.assertEqual(len(second.context["vendor_products"]), 1)
        self.assertContains(first, 'class="pagination"')

    def test_vendor_orders_are_paginated(self):
        vendor = make_vendor()
        product = make_product(vendor=vendor, price=Decimal("10.00"))
        for _ in range(21):
            order = make_order(user=make_user())
            OrderItem.objects.create(
                order=order,
                product=product,
                name=product.name,
                price=Decimal("10.00"),
                quantity=1,
            )
        self.client.force_login(vendor)

        first = self.client.get(reverse("vendor_orders"))
        second = self.client.get(reverse("vendor_orders"), {"page": 2})

        self.assertEqual(len(first.context["orders"]), 20)
        self.assertEqual(first.context["page_obj"].paginator.count, 21)
        self.assertEqual(len(second.context["orders"]), 1)
        self.assertContains(first, 'class="pagination"')
