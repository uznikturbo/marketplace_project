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
from django.conf import settings
import requests
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from catalog.models import Cart
import time


def checkout(request):
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
    else:
        session_key = request.session.session_key
        cart = (
            Cart.objects.filter(session_key=session_key).first()
            if session_key
            else None
        )

    if not cart or not cart.items.exists():
        messages.warning(request, "Ваш кошик порожній.")
        return redirect("catalog")

    if request.method == "POST":
        form = OrderCreateForm(request.POST)
        if form.is_valid():
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

                    for item in cart.items.all():
                        product = item.product

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
                        product.save()

                    if request.user.is_authenticated:
                        user = request.user
                        user.first_name = form.cleaned_data.get("first_name")
                        user.last_name = form.cleaned_data.get("last_name")
                        user.middle_name = form.cleaned_data.get("middle_name", "")
                        user.number = form.cleaned_data.get("number")

                        if order.city_ref and order.warehouse_ref:
                            user.default_city = order.city
                            user.default_city_ref = order.city_ref
                            user.default_address = order.address
                            user.default_warehouse_ref = order.warehouse_ref
                        user.save()

                    cart.items.all().delete()

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
                    print(f"[DEBUG] server_url = {server_url}")
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
            except Exception as e:
                print("Error: ", e)
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

    if request.user.is_authenticated and order.user != request.user:
        return redirect("home")

    if not request.user.is_authenticated and order.user is not None:
        return redirect("home")

    liqpay_data_b64 = None
    liqpay_signature = None

    if (
        order.payment_method == PaymentMethod.LIQPAY
        and order.payment_status == PaymentStatus.PENDING
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
    search_query = request.GET.get("q", "")
    payload = {
        "apiKey": settings.NOVAPOST_API,
        "modelName": "Address",
        "calledMethod": "getCities",
        "methodProperties": {"FindByString": search_query, "Limit": "50"},
    }

    response = requests.post("https://api.novaposhta.ua/v2.0/json/", json=payload)
    return JsonResponse(response.json())


def np_get_warehouses(request):
    city_ref = request.GET.get("city_ref")

    if not city_ref:
        return JsonResponse({"success": False, "error": "city_ref is required"})

    payload = {
        "apiKey": settings.NOVAPOST_API,
        "modelName": "Address",
        "calledMethod": "getWarehouses",
        "methodProperties": {"CityRef": city_ref},
    }

    response = requests.post("https://api.novaposhta.ua/v2.0/json/", json=payload)
    return JsonResponse(response.json())


@login_required
def order_pay(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if order.payment_method != PaymentMethod.LIQPAY:
        messages.error(request, "Це замовлення не передбачає онлайн-оплати карткою.")
        return redirect("profile_orders")

    if order.payment_status == PaymentStatus.PAID:
        messages.warning(request, "Замовлення вже оплачено!")
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
    print(f"[DEBUG] server_url = {server_url}")
    return render(
        request,
        "orders/liqpay_redirect.html",
        {"data": liqpay_data_b64, "signature": liqpay_signature},
    )
