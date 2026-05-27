from django.contrib import admin
from .models import CustomUser
from django.contrib.auth.admin import UserAdmin


# Register your models here.
class CustomUserAdmin(UserAdmin):
    model = CustomUser

    ordering = ("number",)
    list_display = (
        "id",
        "number",
        "email",
        "first_name",
        "last_name",
        "is_vendor",
        "confirmed",
        "is_staff",
        "is_active",
    )
    list_filter = ("is_vendor", "confirmed", "is_staff", "is_active")
    fieldsets = (
        (None, {"fields": ("number", "password")}),
        ("Personal Info", {"fields": ("email", "first_name", "last_name")}),
        (
            "Permissions",
            {"fields": ("is_vendor", "confirmed", "is_staff", "is_active")},
        ),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("number", "password1", "password2")}),
    )


admin.site.register(CustomUser, CustomUserAdmin)
