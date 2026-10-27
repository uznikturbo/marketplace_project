from .utils import get_cart, get_favorite_ids


def cart(request):
    return {"cart": get_cart(request)}


def user_favorites(request):
    return {"user_favorite_ids": get_favorite_ids(request)}
