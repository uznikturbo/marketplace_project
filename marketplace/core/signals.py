from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from catalog.models import Category, Product


@receiver([post_delete, post_save], sender=Product)
def invalidate_product_cache(sender, instance, **kwargs):
    cache.delete(f"product_detail_{instance.pk}")

    cache.delete("home_latest_products")


@receiver([post_delete, post_save], sender=Category)
def invalidate_category_cache(sender, instance, **kwargs):
    cache.delete("all_categories")
    cache.delete("all_root_categories")
    cache.delete("nav_categories")

    cache.delete(f"category_sub_ids_{instance.pk}")

    if instance.parent:
        cache.delete(f"category_sub_ids_{instance.parent.id}")
