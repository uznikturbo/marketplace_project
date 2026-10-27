from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect


def vendor_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)

        if not request.user.is_vendor:
            messages.error(request, "Ви повинні бути вендором")
            return redirect("profile")

        return view_func(request, *args, **kwargs)

    return wrapper
