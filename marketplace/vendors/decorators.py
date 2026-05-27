from django.shortcuts import redirect
from django.contrib import messages


def vendor_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated and not request.user.is_vendor:
            messages.error(request, "Ви повинні бути вендором")
            return redirect("profile")
        return view_func(request, *args, **kwargs)

    return wrapper
