from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory

from catalog.models import Product, ProductDiscount, ProductImage


class CreateProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            "name",
            "description",
            "price",
            "quantity",
            "category",
            "properties",
        )

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price is not None and price < Decimal("0"):
            raise forms.ValidationError("Ціна не може бути від'ємною.")
        return price


ProductImageFormSet = inlineformset_factory(
    Product,
    ProductImage,
    fields=("image_url",),
    extra=3,
    widgets={
        "image_url": forms.URLInput(
            attrs={"class": "form-control", "placeholder": "URL картинки"}
        )
    },
    can_delete=True,
)


class CreateProductDiscountForm(forms.ModelForm):
    class Meta:
        model = ProductDiscount
        fields = ("value", "start_at", "end_at")
        widgets = {
            "start_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "end_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
