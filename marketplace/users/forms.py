from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserChangeForm

User = get_user_model()


class CustomUserChangeForm(UserChangeForm):
    password = None

    class Meta:
        model = User
        fields = ("first_name", "last_name", "number", "email")

    def clean_email(self):
        email = self.cleaned_data.get("email")

        if not email:
            return email

        email = email.lower().strip()

        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Користувач з такою поштою вже існує")

        return email
