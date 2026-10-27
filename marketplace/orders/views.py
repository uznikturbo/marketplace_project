from decimal import Decimal
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from .models import Order, OrderItem, PaymentMethod, PaymentStatus
from .forms import OrderCreateForm
import base64
import hashlib
import json
import logging
from django.conf import settings
import requests
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from catalog.models import Product
from catalog.utils import get_cart
import time

logger = logging.getLogger(__name__)


def _liqpay_is_configured():
    return bool(settings.LIQPAY_PUBLIC_KEY and settings.LIQPAY_PRIVATE_KEY)


def checkout(request):
    cart = get_cart(request)

    if not cart or not cart.items.exists():
        messages.warning(request, "Ваш кошик порожній.")
        return redirect("catalog")

    if request.method == "POST":
        form = OrderCreateForm(request.POST)
        if form.is_valid():
            if (
                form.cleaned_data.get("payment_method") == PaymentMethod.LIQPAY
                and not _liqpay_is_configured()
            ):
                messages.error(
                    request,
                    "Онлайн-оплата тимчасово недоступна. Оберіть післяплату.",
                )
                return redirect("checkout")

            try:
                with transaction.atomic():
                    order = form.save(commit=False)
                    if request.user.is_authenticated:
                        order.user = request.user

                    cart_total = cart.get_total_price()
                    order.total_products = cart_total

                    if order.payment_method == PaymentMethod.POSTPAID:
                        fee = Decimal("20.00") + (cart_total * Decimal("0.02"))
                        order.postpaid_fee = round(fee, 2)
                    else:
                        order.postpaid_fee = Decimal("0.00")

                    order.total_amount = order.total_products + order.postpaid_fee
                    order.save()

                    for item in cart.items.select_related("product").all():
                        # Блокуємо рядок товару, щоб два замовлення одночасно
                        # не могли продати більше, ніж є на складі.
                        product = Product.objects.select_for_update().get(
                            pk=item.product_id
                        )

                        if not product.is_available:
                            raise ValueError(
                                f"Товар '{product.name}' більше недоступний."
                            )

                        if product.quantity < item.quantity:
                            raise ValueError(
                                f"Товару '{product.name}' залишилось лише {product.quantity} шт."
                            )

                        OrderItem.objects.create(
                            order=order,
                            product=product,
                            name=product.name,
                            price=product.get_current_price,
                            quantity=item.quantity,
                        )

                        product.quantity -= item.quantity
                        product.save(update_fields=["quantity"])

                    if request.user.is_authenticated:
                        user = request.user
                        user.first_name = form.cleaned_data.get("first_name")
                        user.last_name = form.cleaned_data.get("last_name")
                        user.middle_name = form.cleaned_data.get("middle_name", "")
                        user.number = form.cleaned_data.get("number")

                        if order.city_ref:
                            user.default_city = order.city
                            user.default_city_ref = order.city_ref
                            user.default_address = order.address
                            user.default_warehouse_ref = order.warehouse_ref
                        user.save()

                    cart.items.all().delete()

                # Запам'ятовуємо замовлення в сесії, щоб гість міг бачити
                # сторінку успіху, але не міг переглядати чужі замовлення.
                guest_order_ids = request.session.get("guest_order_ids", [])
                if order.id not in guest_order_ids:
                    guest_order_ids.append(order.id)
                    request.session["guest_order_ids"] = guest_order_ids

                if order.payment_method == PaymentMethod.LIQPAY:
                    result_url = request.build_absolute_uri(
                        reverse("order_success", args=[order.id])
                    )
                    server_url = request.build_absolute_uri(reverse("liqpay_callback"))

                    liqpay_params = {
                        "public_key": settings.LIQPAY_PUBLIC_KEY,
                        "version": "3",
                        "action": "pay",
                        "amount": str(order.total_amount),
                        "currency": "UAH",
                        "description": f"Оплата замовлення #{order.id}",
                        "order_id": f"{order.id}_{int(time.time())}",
                        "result_url": result_url,
                        "server_url": server_url,
                    }

                    json_data = json.dumps(liqpay_params)
                    liqpay_data_b64 = base64.b64encode(
                        json_data.encode("utf-8")
                    ).decode("utf-8")

                    sign_string = (
                        settings.LIQPAY_PRIVATE_KEY
                        + liqpay_data_b64
                        + settings.LIQPAY_PRIVATE_KEY
                    )
                    liqpay_signature = base64.b64encode(
                        hashlib.sha1(sign_string.encode("utf-8")).digest()
                    ).decode("utf-8")

                    return render(
                        request,
                        "orders/liqpay_redirect.html",
                        {"data": liqpay_data_b64, "signature": liqpay_signature},
                    )
                else:
                    return redirect("order_success", order_id=order.id)

            except ValueError as e:
                messages.error(request, str(e))
                return redirect("checkout")
            except Exception:
                logger.exception("Unexpected error while creating order")
                messages.error(request, "Сталася системна помилка. Спробуйте ще раз.")
                return redirect("checkout")

    else:
        initial_data = {}
        if request.user.is_authenticated:
            initial_data = {
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
                "middle_name": request.user.middle_name,
                "number": request.user.number,
                "email": request.user.email,
                "city": request.user.default_city,
                "city_ref": request.user.default_city_ref,
                "address": request.user.default_address,
                "warehouse_ref": request.user.default_warehouse_ref,
            }
        form = OrderCreateForm(initial=initial_data)

    return render(request, "orders/checkout.html", {"form": form, "cart": cart})


def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    guest_order_ids = request.session.get("guest_order_ids", [])

    if request.user.is_authenticated:
        if order.user_id is not None:
            if order.user_id != request.user.id:
                return redirect("home")
        elif order.id not in guest_order_ids:
            return redirect("home")
    else:
        if order.user_id is not None or order.id not in guest_order_ids:
            return redirect("home")

    liqpay_data_b64 = None
    liqpay_signature = None

    if (
        order.payment_method == PaymentMethod.LIQPAY
        and order.payment_status == PaymentStatus.PENDING
        and _liqpay_is_configured()
    ):
        result_url = request.build_absolute_uri(
            reverse("order_success", args=[order.id])
        )
        server_url = request.build_absolute_uri(reverse("liqpay_callback"))

        liqpay_params = {
            "public_key": settings.LIQPAY_PUBLIC_KEY,
            "version": "3",
            "action": "pay",
            "amount": str(order.total_amount),
            "currency": "UAH",
            "description": f"Оплата замовлення #{order.id}",
            "order_id": f"{order.id}_{int(time.time())}",
            "result_url": result_url,
            "server_url": server_url,
        }

        json_data = json.dumps(liqpay_params)
        liqpay_data_b64 = base64.b64encode(json_data.encode("utf-8")).decode("utf-8")

        sign_string = (
            settings.LIQPAY_PRIVATE_KEY + liqpay_data_b64 + settings.LIQPAY_PRIVATE_KEY
        )
        liqpay_signature = base64.b64encode(
            hashlib.sha1(sign_string.encode("utf-8")).digest()
        ).decode("utf-8")

    return render(
        request,
        "orders/success.html",
        {
            "order": order,
            "liqpay_data": liqpay_data_b64,
            "liqpay_signature": liqpay_signature,
        },
    )


def np_get_cities(request):
    if not settings.NOVAPOST_API:
        return JsonResponse(
            {"success": False, "error": "Nova Poshta API key is not configured"},
            status=503,
        )

    search_query = request.GET.get("q", "")
    payload = {
        "apiKey": settings.NOVAPOST_API,
        "modelName": "Address",
        "calledMethod": "getCities",
        "methodProperties": {"FindByString": search_query, "Limit": "50"},
    }

    try:
        response = requests.post(
            "https://api.novaposhta.ua/v2.0/json/", json=payload, timeout=10
        )
        response.raise_for_status()
        return JsonResponse(response.json())
    except (requests.RequestException, ValueError):
        return JsonResponse(
            {"success": False, "error": "Nova Poshta API is unavailable"},
            status=502,
        )


def np_get_warehouses(request):
    if not settings.NOVAPOST_API:
        return JsonResponse(
            {"success": False, "error": "Nova Poshta API key is not configured"},
            status=503,
        )

    city_ref = request.GET.get("city_ref")

    if not city_ref:
        return JsonResponse({"success": False, "error": "city_ref is required"})

    payload = {
        "apiKey": settings.NOVAPOST_API,
        "modelName": "Address",
        "calledMethod": "getWarehouses",
        "methodProperties": {"CityRef": city_ref},
    }

    try:
        response = requests.post(
            "https://api.novaposhta.ua/v2.0/json/", json=payload, timeout=10
        )
        response.raise_for_status()
        return JsonResponse(response.json())
    except (requests.RequestException, ValueError):
        return JsonResponse(
            {"success": False, "error": "Nova Poshta API is unavailable"},
            status=502,
        )


@login_required
def order_pay(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.payment_method != PaymentMethod.LIQPAY:
        messages.error(request, "Це замовлення не передбачає онлайн-оплати карткою.")
        return redirect("profile_orders")

    if order.payment_status == PaymentStatus.PAID:
        messages.warning(request, "Замовлення вже оплачено!")
        return redirect("profile_orders")

    if not _liqpay_is_configured():
        messages.error(request, "Онлайн-оплата тимчасово недоступна.")
        return redirect("profile_orders")

    result_url = request.build_absolute_uri(reverse("order_success", args=[order.id]))
    server_url = request.build_absolute_uri(reverse("liqpay_callback"))

    liqpay_params = {
        "public_key": settings.LIQPAY_PUBLIC_KEY,
        "version": "3",
        "action": "pay",
        "amount": str(order.total_amount),
        "currency": "UAH",
        "description": f"Оплата замовлення #{order.id}",
        "order_id": f"{order.id}_{int(time.time())}",
        "result_url": result_url,
        "server_url": server_url,
    }

    json_data = json.dumps(liqpay_params)
    liqpay_data_b64 = base64.b64encode(json_data.encode("utf-8")).decode("utf-8")

    sign_string = (
        settings.LIQPAY_PRIVATE_KEY + liqpay_data_b64 + settings.LIQPAY_PRIVATE_KEY
    )
    liqpay_signature = base64.b64encode(
        hashlib.sha1(sign_string.encode("utf-8")).digest()
    ).decode("utf-8")

    return render(
        request,
        "orders/liqpay_redirect.html",
        {"data": liqpay_data_b64, "signature": liqpay_signature},
    )
