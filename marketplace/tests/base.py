"""Shared helpers for the test suite.

The project uses Redis for caching in development, so every test case
switches to an in-memory cache. Passwords use a fast hasher to keep the
suite quick.
"""

from decimal import Decimal
from itertools import count

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from catalog.models import Cart, Category, Product
from orders.models import DeliveryMethod, Order, PaymentMethod

User = get_user_model()

LOCMEM_CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "marketplace-tests",
    }
}

FAST_PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

_counter = count(1)


@override_settings(CACHES=LOCMEM_CACHE, PASSWORD_HASHERS=FAST_PASSWORD_HASHERS)
class BaseTestCase(TestCase):
    """Base class that isolates cache state between tests."""

    def setUp(self):
        super().setUp()
        cache.clear()

    def tearDown(self):
        cache.clear()
        super().tearDown()


def make_user(number=None, email=None, password="StrongPass123!", **kwargs):
    n = next(_counter)
    number = number or f"+38050{n:07d}"
    email = email or f"user{n}@example.com"
    return User.objects.create_user(
        number=number, email=email, password=password, **kwargs
    )


def make_vendor(**kwargs):
    return make_user(is_vendor=True, **kwargs)


def make_category(name=None, parent=None):
    n = next(_counter)
    return Category.objects.create(name=name or f"Category {n}", parent=parent)


def make_product(vendor=None, category=None, **kwargs):
    vendor = vendor or make_vendor()
    category = category or make_category()
    n = next(_counter)
    defaults = {
        "name": f"Product {n}",
        "description": "Test product description",
        "price": Decimal("100.00"),
        "quantity": 10,
        "is_available": True,
    }
    defaults.update(kwargs)
    return Product.objects.create(user=vendor, category=category, **defaults)


def make_cart(user=None, session_key=None):
    return Cart.objects.create(user=user, session_key=session_key)


def make_order(user=None, **kwargs):
    defaults = {
        "first_name": "Ivan",
        "last_name": "Petrenko",
        "number": "+380501112233",
        "email": "ivan@example.com",
        "delivery_method": DeliveryMethod.NP_BRANCH,
        "city": "Kyiv",
        "address": "Branch 1",
        "payment_method": PaymentMethod.POSTPAID,
        "total_products": Decimal("100.00"),
        "total_amount": Decimal("100.00"),
    }
    defaults.update(kwargs)
    return Order.objects.create(user=user, **defaults)


def checkout_payload(**overrides):
    payload = {
        "first_name": "Ivan",
        "last_name": "Petrenko",
        "middle_name": "",
        "number": "+380501112233",
        "email": "ivan@example.com",
        "delivery_method": DeliveryMethod.NP_BRANCH,
        "city": "Kyiv",
        "city_ref": "city-ref",
        "address": "Branch 1",
        "warehouse_ref": "warehouse-ref",
        "payment_method": PaymentMethod.POSTPAID,
        "comment": "",
    }
    payload.update(overrides)
    return payload
