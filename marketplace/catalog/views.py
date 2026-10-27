from django.shortcuts import render, get_object_or_404, redirect
from . import models
from .decorators import confirmed_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from .utils import get_user_cart, get_all_subcategories_ids, get_favorite_ids
from .models import CartItem
from django.db.models import Q
from django.http import JsonResponse
from django.core.cache import cache


# Create your views here.
def catalog_view(request):
    query = request.GET.get("q")
    raw_category_id = request.GET.get("category")

    current_category_id = None
    if raw_category_id:
        try:
            current_category_id = int(raw_category_id)
        except (TypeError, ValueError):
            current_category_id = None

    categories = cache.get("all_root_categories")
    if not categories:
        categories = list(models.Category.objects.filter(parent=None))
        cache.set("all_root_categories", categories, timeout=60 * 60 * 24)

    products = models.Product.objects.filter(is_available=True)

    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        ).distinct()

    if current_category_id is not None:
        subcat_cache_key = f"category_sub_ids_{current_category_id}"
        all_ids = cache.get(subcat_cache_key)

        if all_ids is None:
            try:
                current_category = models.Category.objects.get(id=current_category_id)
                all_ids = get_all_subcategories_ids(current_category)
                cache.set(subcat_cache_key, all_ids, timeout=60 * 60 * 24)
            except models.Category.DoesNotExist:
                all_ids = []

        if all_ids:
            products = products.filter(category_id__in=all_ids)
        else:
            # Неіснуюча категорія не повинна показувати весь каталог.
            products = products.none()

    return render(
        request,
        "catalog/catalog.html",
        {
            "products": products,
            "categories": categories,
            "query": query,
            "current_category_id": current_category_id,
            "user_favorite_ids": get_favorite_ids(request),
        },
    )


def product_detail_view(request, pk):
    cache_key = f"product_detail_{pk}"
    product = cache.get(cache_key)

    if not product:
        product = get_object_or_404(models.Product, pk=pk)
        cache.set(cache_key, product, timeout=60 * 15)

    return render(
        request,
        "catalog/product_detail.html",
        {"product": product, "user_favorite_ids": get_favorite_ids(request)},
    )


@confirmed_required
@require_POST
def submit_review(request, pk):
    product = get_object_or_404(models.Product, pk=pk)

    try:
        rating = int(request.POST.get("rating", 0))
    except (TypeError, ValueError):
        rating = 0

    review_text = request.POST.get("review", "").strip()

    if 1 <= rating <= 5:
        models.ProductRating.objects.create(
            product=product,
            user=request.user,
            rating=rating,
            review=review_text,
        )
        messages.success(request, "Дякуємо за ваш відгук!")
    else:
        messages.error(request, "Будь ласка, оберіть оцінку від 1 до 5.")

    cache.delete(f"product_detail_{pk}")

    # Redirect після POST, щоб оновлення сторінки не створювало дубль відгуку.
    return redirect("product_detail", pk=pk)


@require_POST
def cart_add(request, pk):
    cart = get_user_cart(request)
    product = get_object_or_404(models.Product, pk=pk)

    if not product.is_available or product.quantity <= 0:
        messages.error(request, f"Товар '{product.name}' немає в наявності.")
        return redirect(request.META.get("HTTP_REFERER", "/"))

    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(quantity, 1)

    override = request.POST.get("override_quantity", "False") == "True"

    cart_item, created = cart.items.get_or_create(cart=cart, product=product)

    if override or created:
        new_quantity = quantity
    else:
        new_quantity = cart_item.quantity + quantity

    if new_quantity > product.quantity:
        new_quantity = product.quantity
        messages.warning(
            request, f"Доступно лише {product.quantity} шт. товару '{product.name}'."
        )

    cart_item.quantity = new_quantity
    cart_item.save()
    messages.success(request, f"Товар '{product.name}' додано до кошика.")
    return redirect(request.META.get("HTTP_REFERER", "/"))


@require_POST
def cart_remove(request, pk):
    cart = get_user_cart(request)

    CartItem.objects.filter(cart=cart, product_id=pk).delete()
    messages.success(request, "Товар видалено з кошика.")
    return redirect(request.META.get("HTTP_REFERER", "/"))


def cart_detail_view(request):
    cart = get_user_cart(request)
    return render(request, "catalog/cart_detail.html", {"cart": cart})


@require_POST
def cart_update(request, pk):
    cart = get_user_cart(request)
    product = get_object_or_404(models.Product, pk=pk)

    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(quantity, 1)

    if product.quantity > 0:
        quantity = min(quantity, product.quantity)

    cart_item, created = cart.items.get_or_create(cart=cart, product=product)
    cart_item.quantity = quantity
    cart_item.save()

    messages.success(request, f"Кількість товару '{product.name}' оновлено.")
    return redirect(request.META.get("HTTP_REFERER", "/"))


def toggle_favorite(request, pk):
    product = get_object_or_404(models.Product, pk=pk)

    if request.user.is_authenticated:
        favorite, created = models.Favorite.objects.get_or_create(
            user=request.user, product=product
        )
        if not created:
            favorite.delete()
            status = "removed"
        else:
            status = "added"
    else:
        favorites = request.session.get("favorites", [])

        if pk in favorites:
            favorites.remove(pk)
            status = "removed"
        else:
            favorites.append(pk)
            status = "added"

        request.session["favorites"] = favorites

    return JsonResponse({"status": status})


def wishlist_view(request):
    if request.user.is_authenticated:
        favorites = (
            models.Favorite.objects.filter(user=request.user)
            .select_related("product")
            .order_by("-created_at")
        )
        products = [f.product for f in favorites]
    else:
        favorite_ids = request.session.get("favorites", [])
        products = list(models.Product.objects.filter(id__in=favorite_ids))

    return render(
        request,
        "catalog/wishlist.html",
        {"products": products, "user_favorite_ids": get_favorite_ids(request)},
    )
