from django.db import transaction

from catalog.models import Product

from .models import (
    Order,
    OrderItem,
    OrderItemStatus,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)


class OrderItemCancellationError(Exception):
    """Raised when an order item cannot be cancelled by a vendor."""


@transaction.atomic
def cancel_order_item(item: OrderItem) -> OrderItem:
    """Cancel one order item and restore its stock.

    The parent order is cancelled only when every item in it is cancelled.
    Totals are recalculated from the remaining active items.
    """
    item = (
        OrderItem.objects.select_for_update()
        .select_related("order")
        .get(pk=item.pk)
    )
    order = Order.objects.select_for_update().get(pk=item.order_id)

    if item.status == OrderItemStatus.CANCELLED:
        raise OrderItemCancellationError("Цей товар уже скасовано.")

    if order.status in (
        OrderStatus.SHIPPED,
        OrderStatus.COMPLETED,
        OrderStatus.CANCELLED,
    ):
        raise OrderItemCancellationError(
            "Не можна скасувати товар у відправленому, виконаному або скасованому замовленні."
        )

    if (
        order.payment_method == PaymentMethod.LIQPAY
        and order.payment_status == PaymentStatus.PENDING
    ):
        raise OrderItemCancellationError(
            "Не можна змінювати позицію LiqPay-замовлення до завершення оплати."
        )

    if item.product_id:
        product = Product.objects.select_for_update().get(pk=item.product_id)
        product.quantity += item.quantity
        product.save(update_fields=["quantity"])

    item.status = OrderItemStatus.CANCELLED
    item.save(update_fields=["status"])

    order.recalculate_totals()
    if not order.items.exclude(status=OrderItemStatus.CANCELLED).exists():
        order.status = OrderStatus.CANCELLED

    order.save(
        update_fields=[
            "total_products",
            "postpaid_fee",
            "total_amount",
            "status",
            "updated_at",
        ]
    )
    return item
