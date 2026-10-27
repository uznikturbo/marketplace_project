from django import forms
from .models import Order


class OrderCreateForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = [
            "first_name",
            "last_name",
            "middle_name",
            "number",
            "email",
            "delivery_method",
            "city",
            "city_ref",
            "address",
            "warehouse_ref",
            "payment_method",
            "comment",
        ]
        widgets = {
            "city_ref": forms.HiddenInput(),
            "warehouse_ref": forms.HiddenInput(),
            "comment": forms.Textarea(attrs={"rows": 3, "placeholder": "Коментар"}),
            "delivery_method": forms.RadioSelect(),
            "payment_method": forms.RadioSelect(),
        }
