from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase
from django.utils import timezone

from catalog.models import CartItem, ProductDiscount, ProductRating
from catalog.utils import get_all_subcategories_ids
from users.models import normalize_number

from .base import BaseTestCase, make_cart, make_category, make_product, make_user


class NormalizeNumberTests(SimpleTestCase):
    def test_keeps_already_normalized_number(self):
        self.assertEqual(normalize_number("+380501112233"), "+380501112233")

    def test_adds_plus_to_country_code(self):
        self.assertEqual(normalize_number("380501112233"), "+380501112233")

    def test_adds_country_code_to_local_number(self):
        self.assertEqual(normalize_number("0501112233"), "+380501112233")

    def test_keeps_other_country_prefix(self):
        self.assertEqual(normalize_number("+15551234567"), "+15551234567")

    def test_strips_whitespace(self):
        self.assertEqual(normalize_number("  +380501112233  "), "+380501112233")

    def test_empty_values_are_returned_as_is(self):
        self.assertIsNone(normalize_number(None))
        self.assertEqual(normalize_number(""), "")


class UserModelTests(BaseTestCase):
    def test_phone_is_normalized_on_save(self):
        user = make_user(number="0501112233")
        user.refresh_from_db()
        self.assertEqual(user.number, "+380501112233")

    def test_email_is_lowercased_and_stripped_on_save(self):
        user = make_user(email="  Mixed.Case@Example.COM ")
        user.refresh_from_db()
        self.assertEqual(user.email, "mixed.case@example.com")

    def test_duplicate_email_is_rejected_case_insensitively(self):
        make_user(email="duplicate@example.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_user(email="DUPLICATE@example.com")

    def test_duplicate_phone_is_rejected_after_normalization(self):
        make_user(number="+380501112233")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_user(number="0501112233")

    def test_changing_phone_number_unconfirms_user(self):
        user = make_user()
        user.confirmed = True
        user.save()

        user.number = "0509998877"
        user.save()
        user.refresh_from_db()

        self.assertFalse(user.confirmed)

    def test_saving_with_same_phone_keeps_confirmation(self):
        user = make_user(number="+380501112233")
        user.confirmed = True
        user.save()

        user.first_name = "Ivan"
        user.save()
        user.refresh_from_db()

        self.assertTrue(user.confirmed)


class CategoryTests(BaseTestCase):
    def test_str_contains_full_path(self):
        root = make_category(name="Electronics")
        child = make_category(name="Phones", parent=root)
        grandchild = make_category(name="Smartphones", parent=child)

        self.assertEqual(
            str(grandchild), "Electronics -> Phones -> Smartphones"
        )

    def test_subcategory_ids_include_whole_tree(self):
        root = make_category()
        child = make_category(parent=root)
        grandchild = make_category(parent=child)
        other = make_category()

        ids = get_all_subcategories_ids(root)

        self.assertCountEqual(ids, [root.id, child.id, grandchild.id])
        self.assertNotIn(other.id, ids)


class ProductModelTests(BaseTestCase):
    def test_average_rating_and_count(self):
        product = make_product()
        ProductRating.objects.create(product=product, user=make_user(), rating=5)
        ProductRating.objects.create(product=product, user=make_user(), rating=4)

        self.assertEqual(product.ratings_count, 2)
        self.assertEqual(product.average_rating, 4.5)
        self.assertEqual(product.rating_percentage, 90.0)

    def test_rating_defaults_when_there_are_no_reviews(self):
        product = make_product()

        self.assertEqual(product.average_rating, 0.0)
        self.assertEqual(product.ratings_count, 0)
        self.assertEqual(product.rating_percentage, 0.0)

    def test_current_price_without_discount(self):
        product = make_product(price=Decimal("200.00"))

        self.assertFalse(product.is_discounted)
        self.assertEqual(product.get_current_price, Decimal("200.00"))

    def test_current_price_with_active_discount(self):
        product = make_product(price=Decimal("200.00"))
        now = timezone.now()
        ProductDiscount.objects.create(
            product=product,
            value=25,
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=1),
        )

        self.assertTrue(product.is_discounted)
        self.assertEqual(product.get_current_price, Decimal("150.00"))

    def test_expired_discount_is_ignored(self):
        product = make_product(price=Decimal("200.00"))
        now = timezone.now()
        ProductDiscount.objects.create(
            product=product,
            value=50,
            start_at=now - timedelta(days=5),
            end_at=now - timedelta(days=1),
        )

        self.assertFalse(product.is_discounted)
        self.assertEqual(product.get_current_price, Decimal("200.00"))

    def test_future_discount_is_ignored(self):
        product = make_product(price=Decimal("200.00"))
        now = timezone.now()
        ProductDiscount.objects.create(
            product=product,
            value=50,
            start_at=now + timedelta(days=1),
            end_at=now + timedelta(days=5),
        )

        self.assertFalse(product.is_discounted)
        self.assertEqual(product.get_current_price, Decimal("200.00"))


class ProductDiscountValidationTests(BaseTestCase):
    def _discount(self, **kwargs):
        product = make_product()
        now = timezone.now()
        defaults = {
            "product": product,
            "value": 10,
            "start_at": now,
            "end_at": now + timedelta(days=1),
        }
        defaults.update(kwargs)
        return ProductDiscount(**defaults)

    def test_valid_discount_passes_validation(self):
        self._discount().full_clean()

    def test_zero_value_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._discount(value=0).full_clean()

    def test_value_above_hundred_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._discount(value=101).full_clean()

    def test_end_date_before_start_date_is_rejected(self):
        now = timezone.now()
        with self.assertRaises(ValidationError):
            self._discount(start_at=now, end_at=now - timedelta(hours=1)).full_clean()


class CartModelTests(BaseTestCase):
    def test_item_total_price_uses_current_price(self):
        product = make_product(price=Decimal("100.00"))
        cart = make_cart(user=make_user())
        item = CartItem.objects.create(cart=cart, product=product, quantity=3)

        self.assertEqual(item.get_total_price(), Decimal("300.00"))

    def test_cart_totals_with_discount(self):
        product = make_product(price=Decimal("200.00"))
        now = timezone.now()
        ProductDiscount.objects.create(
            product=product,
            value=50,
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=1),
        )
        cart = make_cart(user=make_user())
        CartItem.objects.create(cart=cart, product=product, quantity=2)

        self.assertEqual(cart.get_total_price(), Decimal("200.00"))
        self.assertEqual(cart.get_raw_total_price(), Decimal("400.00"))
        self.assertEqual(cart.get_discount_amount(), Decimal("200.00"))

    def test_empty_cart_totals_are_zero(self):
        cart = make_cart(user=make_user())

        self.assertEqual(cart.get_total_price(), 0)
        self.assertEqual(cart.get_raw_total_price(), 0)
        self.assertEqual(cart.get_discount_amount(), 0)
