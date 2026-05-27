from django.shortcuts import redirect


def confirmed_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.confirmed:
            return redirect("profile")
        return view_func(request, *args, **kwargs)

    return wrapper
