from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from .models import Cart, CartItem


@receiver(user_logged_in)
def merge_carts_on_login(sender, request, user, **kwargs):
    session_key = request.session.session_key
    if session_key:
        guest_cart = Cart.objects.filter(session_key=session_key).first()

        if guest_cart and guest_cart.items.exists():
            user_cart, created = Cart.objects.get_or_create(user=user)

            for item in guest_cart.items.all():
                user_item, item_created = CartItem.objects.get_or_create(
                    cart=user_cart, product=item.product
                )
                if not item_created:
                    user_item.quantity += item.quantity
                    user_item.save()
                else:
                    user_item.quantity = item.quantity
                    user_item.save()
            guest_cart.delete()
