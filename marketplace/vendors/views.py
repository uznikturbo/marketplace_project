from django.shortcuts import render, redirect, get_object_or_404
from .decorators import vendor_required
from catalog.models import Product
from .forms import CreateProductForm, ProductImageFormSet, CreateProductDiscountForm
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone
from orders.models import Order, PaymentStatus, OrderStatus
from django.db.models import Q, F, Sum
from datetime import timedelta


# Create your views here.
@vendor_required
def vendor_view(request):
    vendor_products = Product.objects.filter(user=request.user)
    return render(
        request,
        "vendors/vendor.html",
        {"vendor_products": vendor_products},
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
            filter=Q(items__product__user=vendor),
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
                filter=Q(items__product__user=vendor),
            )
        )["total"]
        or 0
    )

    total_orders_count = stats_orders.count()

    context = {
        "orders": orders.order_by("-created_at"),
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

    order = get_object_or_404(Order, pk=pk, items__product__user=vendor)

    vendor_items = order.items.filter(product__user=vendor).select_related("product")

    vendor_total = sum(item.total for item in vendor_items)

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in dict(OrderStatus.choices):
            order.status = new_status
            order.save()
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
        "order_statuses": OrderStatus.choices,
    }
    return render(request, "vendors/order_detail.html", context)
