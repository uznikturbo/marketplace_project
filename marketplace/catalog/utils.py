from .models import Cart, Favorite


def get_user_cart(request):
    if request.user.is_authenticated:
        cart, created = Cart.objects.get_or_create(user=request.user)
    else:
        if not request.session.session_key:
            request.session.create()
        # Запам'ятовуємо ключ сесії в даних сесії: Django змінює session_key
        # під час login(), і без цього гостьовий кошик не знаходився б для злиття.
        request.session["cart_session_key"] = request.session.session_key
        cart, created = Cart.objects.get_or_create(
            session_key=request.session.session_key
        )
    return cart


def get_cart(request):
    """Повертає існуючий кошик, не створюючи новий на кожен запит."""
    if request.user.is_authenticated:
        return Cart.objects.filter(user=request.user).first()

    session_key = (
        request.session.get("cart_session_key") or request.session.session_key
    )
    if not session_key:
        return None
    return Cart.objects.filter(session_key=session_key).first()


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
