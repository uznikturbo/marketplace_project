from django import forms
from catalog.models import Product, ProductImage, ProductDiscount
from django.forms import inlineformset_factory


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


ProductImageFormSet = inlineformset_factory(
    Product,
    ProductImage,
    fields=("image_url",),
    extra=3,
    widgets={
        "url": forms.URLInput(
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
