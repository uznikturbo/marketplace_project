from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from catalog.models import Favorite
from catalog.utils import get_favorite_ids

from .forms import CustomUserChangeForm
from orders.models import Order
from django.http import JsonResponse
from django.core.cache import cache
from django.views.decorators.http import require_POST
from registration.utils import generate_code
import json
from registration.tasks import send_sms_conf_task


@login_required
def profile_view(request):
    if request.method == "POST":
        form = CustomUserChangeForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Профіль оновлено!")
            return redirect("profile")
        else:
            messages.error(
                request, "Помилка оновлення профілю. Перевірте введені дані."
            )
    else:
        form = CustomUserChangeForm(instance=request.user)
    return render(request, "users/profile.html", {"user": request.user, "form": form})


@login_required
def profile_wishlist_view(request):
    favorites = (
        Favorite.objects.filter(user=request.user)
        .select_related("product")
        .order_by("-created_at")
    )
    products = [f.product for f in favorites]
    return render(
        request,
        "users/wishlist.html",
        {"products": products, "get_favorite_ids": get_favorite_ids(request)},
    )


@login_required
def profile_orders_view(request):
    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related("items")
        .order_by("-created_at")
    )
    return render(request, "users/orders.html", {"orders": orders})


@login_required
@require_POST
def send_verification_sms_view(request):
    user = request.user

    if user.confirmed:
        return JsonResponse({"error": "Ваш номер вже підтверджено"}, status=400)

    if not user.number:
        return JsonResponse(
            {"error": "У вашому профілі не вказано номер телефону"}, status=400
        )

    lock_key = f"sms_lock_{user.number}"
    if cache.get(lock_key):
        return JsonResponse(
            {"error": "Повторна відправка можлива через 1 хвилину"}, status=429
        )

    code = generate_code()

    cache_key = f"sms_code_{user.number}"
    cache.set(cache_key, code, timeout=300)

    cache.set(lock_key, True, timeout=60)

    send_sms_conf_task.delay(user.number, code)

    return JsonResponse({"status": "Код успішно відправлено у фоні"})


@login_required
@require_POST
def verify_sms_code_view(request):
    user = request.user

    if user.confirmed:
        return JsonResponse({"error": "Ваш номер вже підтверджено"}, status=400)

    try:
        data = json.loads(request.body)
        user_code = data.get("code")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Некоректні дані"}, status=400)

    if not user_code:
        return JsonResponse({"error": "Код не може бути пустим"}, status=400)

    cache_key = f"sms_code_{user.number}"
    saved_code = cache.get(cache_key)

    if saved_code is None:
        return JsonResponse(
            {"error": "Код застарів або не запитувався. Спробуйте ще раз"}, status=400
        )

    if saved_code == str(user_code).strip():
        user.confirmed = True
        user.save(update_fields=["confirmed"])

        cache.delete(cache_key)
        cache.delete(f"sms_lock_{user.number}")

        return JsonResponse(
            {"status": "success", "message": "Номер телефону успішно підтверджено!"}
        )

    return JsonResponse(
        {"error": "Невірний код підтвердження. Спробуйте ще раз"}, status=400
    )
