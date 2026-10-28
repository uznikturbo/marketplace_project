from django.core.cache import cache

from . import models
from .utils import get_cart, get_favorite_ids


def cart(request):
    return {"cart": get_cart(request)}


def user_favorites(request):
    return {"user_favorite_ids": get_favorite_ids(request)}


def nav_categories(request):
    """Top-level categories for the header catalog dropdown."""
    categories = cache.get("nav_categories")
    if categories is None:
        categories = list(
            models.Category.objects.filter(parent=None).order_by("name")
        )
        cache.set("nav_categories", categories, timeout=60 * 60 * 24)
    return {"nav_categories": categories}
