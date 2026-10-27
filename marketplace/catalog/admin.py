from django.contrib import admin

from . import models


# Register your models here.
@admin.register(models.Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "parent")
    search_fields = ("name",)
    list_filter = ("parent",)


class ProductImageInline(admin.TabularInline):
    model = models.ProductImage
    extra = 1
    fields = ("image_url",)


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "price",
        "category",
        "is_available",
        "created_at",
    )
    search_fields = ("name", "description")
    list_filter = ("category", "is_available", "created_at")
    readonly_fields = ("created_at",)

    inlines = [ProductImageInline]


admin.site.register(models.ProductDiscount)
