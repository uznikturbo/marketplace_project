from django.shortcuts import render
from catalog import models as catalog_models
from catalog.utils import get_favorite_ids
from django.core.cache import cache


# Create your views here.
def home_view(request):
    products = cache.get("home_latest_products")
    if not products:
        products = catalog_models.Product.objects.filter(is_available=True).order_by(
            "-created_at"
        )[:10]
        cache.set("home_latest_products", products, timeout=60 * 15)

    categories = cache.get("all_categories")
    if not categories:
        categories = catalog_models.Category.objects.all()
        cache.set("all_categories", categories, timeout=60 * 60 * 24)

    context = {
        "products": products,
        "categories": categories,
        "user_favorite_ids": get_favorite_ids(request),
    }
    return render(request, "core/index.html", context)
