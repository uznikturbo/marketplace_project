from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class DeliveryMethod(models.TextChoices):
    NP_BRANCH = "np_branch", "Нова Пошта (Відділення)"
    NP_POSTOMAT = "np_postomat", "Нова Пошта (Поштомат)"
    NP_COURIER = "np_courier", "Нова Пошта (Кур'єр)"


class PaymentMethod(models.TextChoices):
    LIQPAY = "liqpay", "Безпечна оплата карткою (LiqPay)"
    POSTPAID = "postpaid", "Післяплата (при отриманні)"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Очікує оплати"
    PAID = "paid", "Оплачено"
    FAILED = "failed", "Помилка оплати"


class OrderStatus(models.TextChoices):
    NEW = "new", "Нове замовлення"
    PROCESSING = "processing", "В обробці"
    SHIPPED = "shipped", "Відправлено"
    COMPLETED = "completed", "Виконано"
    CANCELLED = "cancelled", "Скасовано"


class OrderItemStatus(models.TextChoices):
    ACTIVE = "active", "Активний"
    CANCELLED = "cancelled", "Скасований"


class Order(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders"
    )

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100)
    number = models.CharField(max_length=20)
    email = models.EmailField(blank=True)

    delivery_method = models.CharField(max_length=20, choices=DeliveryMethod.choices)

    city = models.CharField(max_length=100)
    city_ref = models.CharField(max_length=36, blank=True)

    address = models.CharField(max_length=255)
    warehouse_ref = models.CharField(max_length=36, blank=True)

    comment = models.TextField(blank=True)

    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    payment_id = models.CharField(max_length=255, blank=True, null=True)

    total_products = models.DecimalField(max_digits=10, decimal_places=2)
    postpaid_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.NEW
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            # Profile: orders of one user, newest first.
            models.Index(
                fields=["user", "-created_at"], name="order_user_created_idx"
            ),
            # Vendor dashboard: filter by status, newest first.
            models.Index(
                fields=["status", "-created_at"], name="order_status_created_idx"
            ),
            # LiqPay callback lookup by payment id.
            models.Index(fields=["payment_id"], name="order_payment_id_idx"),
        ]

    def __str__(self):
        return f"Замовлення #{self.id} - {self.get_status_display()}"

    def recalculate_totals(self):
        """Recalculate totals from the items that are still active."""
        active_items = self.items.exclude(status=OrderItemStatus.CANCELLED)
        total_products = sum(
            (item.total for item in active_items), Decimal("0.00")
        )

        self.total_products = total_products
        if (
            self.payment_method == PaymentMethod.POSTPAID
            and total_products > Decimal("0.00")
        ):
            self.postpaid_fee = round(
                Decimal("20.00") + total_products * Decimal("0.02"), 2
            )
        else:
            self.postpaid_fee = Decimal("0.00")
        self.total_amount = self.total_products + self.postpaid_fee


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=OrderItemStatus.choices,
        default=OrderItemStatus.ACTIVE,
    )

    @property
    def total(self):
        return self.price * self.quantity

    @property
    def is_cancelled(self):
        return self.status == OrderItemStatus.CANCELLED
