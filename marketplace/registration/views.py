from django.shortcuts import render
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import CustomUserCreationForm


def _get_safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")
    if next_url == "None":
        next_url = None
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return None


def login_view(request):
    next_url = _get_safe_next_url(request)

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            identifier = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")

            user = authenticate(request, username=identifier, password=password)

            if user is not None:
                login(request, user)
                messages.success(request, "Успішний вхід!")
                return redirect(next_url or "home")
            else:
                messages.error(request, "Невірний логін або пароль.")
        else:
            messages.error(request, "Помилка входу. Перевірте введені дані.")
    else:
        form = AuthenticationForm()

    return render(
        request, "registration/login.html", {"form": form, "next": next_url}
    )


def register_view(request):
    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
    else:
        form = CustomUserCreationForm()

    return render(request, "registration/register.html", {"form": form})
