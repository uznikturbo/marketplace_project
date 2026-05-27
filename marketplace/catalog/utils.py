from .models import Cart, Favorite


def get_user_cart(request):
    if request.user.is_authenticated:
        cart, created = Cart.objects.get_or_create(user=request.user)
    else:
        if not request.session.session_key:
            request.session.create()
        cart, created = Cart.objects.get_or_create(
            session_key=request.session.session_key
        )
    return cart


def get_all_subcategories_ids(category):
    category_ids = [category.id]
    for subcategory in category.subcategories.all():
        category_ids.extend(get_all_subcategories_ids(subcategory))
    return category_ids


def get_favorite_ids(request):
    if request.user.is_authenticated:
        return list(
            Favorite.objects.filter(user=request.user).values_list(
                "product_id", flat=True
            )
        )
    else:
        return request.session.get("favorites", [])
