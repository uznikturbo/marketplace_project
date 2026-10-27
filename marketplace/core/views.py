import logging

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import render

from catalog import models as catalog_models
from catalog.utils import get_favorite_ids

logger = logging.getLogger(__name__)


def health_view(request):
    """Lightweight health check for uptime probes and load balancers."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Health check failed: database is unavailable")
        return JsonResponse(
            {"status": "error", "database": "unavailable"}, status=503
        )

    return JsonResponse({"status": "ok", "database": "ok"})


def favicon_view(request):
    """Serve the site icon so browsers do not hit a 404 on /favicon.ico."""
    path = settings.BASE_DIR / "static" / "img" / "favicon.ico"
    try:
        return FileResponse(open(path, "rb"), content_type="image/x-icon")
    except FileNotFoundError:
        raise Http404("Favicon not found")


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
