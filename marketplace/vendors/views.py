from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from catalog.models import Product
from core.pagination import paginate
from orders.models import (
    Order,
    OrderItem,
    OrderItemStatus,
    OrderStatus,
    PaymentStatus,
)
from orders.services import OrderItemCancellationError, cancel_order_item

from .decorators import vendor_required
from .forms import CreateProductDiscountForm, CreateProductForm, ProductImageFormSet

VENDOR_PAGE_SIZE = 20


# Create your views here.
@vendor_required
def vendor_view(request):
    vendor_products = (
        Product.objects.filter(user=request.user)
        .select_related("category")
        .prefetch_related("images", "discounts")
        .order_by("-created_at")
    )
    page_obj, page_range = paginate(request, vendor_products, VENDOR_PAGE_SIZE)
    return render(
        request,
        "vendors/vendor.html",
        {
            "vendor_products": page_obj.object_list,
            "page_obj": page_obj,
            "page_range": page_range,
        },
    )


@vendor_required
def create_product(request):
    if request.method == "POST":
        form = CreateProductForm(request.POST)
        formset = ProductImageFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            product = form.save(commit=False)
            product.user = request.user
            product.save()
            formset.instance = product
            formset.save()
            messages.success(
                request, f"Товар '{form.cleaned_data['name']}' успішно додано!"
            )
            return redirect("vendor_view")

        messages.error(request, "Невірно вписані дані. Попробуйте ще раз.")
    else:
        form = CreateProductForm()
        formset = ProductImageFormSet()

    return render(
        request, "vendors/create_product.html", {"form": form, "formset": formset}
    )


@vendor_required
@require_POST
def delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk, user=request.user)
    product.delete()
    messages.success(request, f"Товар '{product.name}' успішно видалено!")
    return redirect("vendor_view")


@vendor_required
def update_product(request, pk):
    product = get_object_or_404(Product, pk=pk, user=request.user)

    if request.method == "POST":
        form = CreateProductForm(request.POST, instance=product)
        formset = ProductImageFormSet(request.POST, instance=product)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f"Товар {product.name} успішно оновлено!")
            return redirect("vendor_view")
    else:
        form = CreateProductForm(instance=product)
        formset = ProductImageFormSet(instance=product)
    return render(
        request,
        "vendors/edit_product.html",
        {"form": form, "product": product, "formset": formset},
    )


@vendor_required
def add_discount(request, pk):
    product = get_object_or_404(Product, pk=pk, user=request.user)

    if request.method == "POST":
        form = CreateProductDiscountForm(request.POST)
        if form.is_valid():
            discount = form.save(commit=False)
            discount.product = product
            discount.save()
            messages.success(
                request, f"Знижку до товару {product.name} успішно додано!"
            )
            return redirect("vendor_view")
    else:
        form = CreateProductDiscountForm()

    return render(
        request, "vendors/add_discount.html", {"form": form, "product": product}
    )


@vendor_required
def vendor_orders_view(request):
    vendor = request.user

    base_orders = Order.objects.filter(items__product__user=vendor).distinct()

    orders = base_orders.annotate(
        vendor_total=Sum(
            F("items__price") * F("items__quantity"),
            filter=Q(
                items__product__user=vendor,
                items__status=OrderItemStatus.ACTIVE,
            ),
        )
    )

    period = request.GET.get("period", "all")
    now = timezone.now()

    if period == "week":
        orders = orders.filter(created_at__gte=now - timedelta(days=7))
    elif period == "month":
        orders = orders.filter(created_at__gte=now - timedelta(days=30))

    status_filter = request.GET.get("status")
    if status_filter:
        orders = orders.filter(status=status_filter)

    stats_orders = base_orders
    if period == "week":
        stats_orders = base_orders.filter(created_at__gte=now - timedelta(days=7))
    elif period == "month":
        stats_orders = base_orders.filter(created_at__gte=now - timedelta(days=30))

    total_revenue = (
        stats_orders.filter(payment_status=PaymentStatus.PAID).aggregate(
            total=Sum(
                F("items__price") * F("items__quantity"),
                filter=Q(
                    items__product__user=vendor,
                    items__status=OrderItemStatus.ACTIVE,
                ),
            )
        )["total"]
        or 0
    )

    total_orders_count = stats_orders.count()

    page_obj, page_range = paginate(
        request, orders.order_by("-created_at"), VENDOR_PAGE_SIZE
    )

    context = {
        "orders": page_obj.object_list,
        "page_obj": page_obj,
        "page_range": page_range,
        "total_revenue": total_revenue,
        "total_orders_count": total_orders_count,
        "period": period,
        "status_filter": status_filter,
        "order_statuses": OrderStatus.choices,
    }
    return render(request, "vendors/orders.html", context)


@vendor_required
def vendor_order_detail(request, pk):
    vendor = request.user

    order = get_object_or_404(
        Order.objects.filter(items__product__user=vendor).distinct(), pk=pk
    )

    vendor_items = order.items.filter(product__user=vendor).select_related("product")

    vendor_total = sum(
        (
            item.total
            for item in vendor_items
            if item.status == OrderItemStatus.ACTIVE
        ),
        Decimal("0.00"),
    )

    if request.method == "POST":
        new_status = request.POST.get("status")
        allowed_statuses = {
            value
            for value, _label in OrderStatus.choices
            if value != OrderStatus.CANCELLED
        }
        if order.status == OrderStatus.CANCELLED:
            messages.error(request, "Скасоване замовлення не можна змінювати.")
        elif new_status in allowed_statuses:
            order.status = new_status
            order.save(update_fields=["status", "updated_at"])
            messages.success(
                request, f"Статус замовлення #{order.id} успішно оновлено!"
            )
            return redirect("vendor_order_details", pk=order.id)
        else:
            messages.error(request, "Недійсний статус.")

    context = {
        "order": order,
        "vendor_items": vendor_items,
        "vendor_total": vendor_total,
        "order_statuses": [
            (value, label)
            for value, label in OrderStatus.choices
            if value != OrderStatus.CANCELLED
        ],
    }
    return render(request, "vendors/order_detail.html", context)


@vendor_required
@require_POST
def vendor_cancel_order_item(request, pk, item_id):
    order = get_object_or_404(
        Order.objects.filter(items__product__user=request.user).distinct(), pk=pk
    )
    item = get_object_or_404(
        OrderItem,
        pk=item_id,
        order=order,
        product__user=request.user,
    )

    try:
        cancel_order_item(item)
    except OrderItemCancellationError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Товар '{item.name}' скасовано.")

    return redirect("vendor_order_details", pk=order.pk)
