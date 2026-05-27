from .utils import get_user_cart


def cart(request):
    return {"cart": get_user_cart(request)}


def user_favorites(request):
    if request.user.is_authenticated:
        fav_ids = list(request.user.favorites.values_list("pk", flat=True))
    else:
        fav_ids = request.session.get("favorites", [])

    return {"user_favorites_ids": fav_ids}
