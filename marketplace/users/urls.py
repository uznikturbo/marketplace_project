from django.urls import path
from . import views

urlpatterns = [
    path("profile/", views.profile_view, name="profile"),
    path("profile/wishlist/", views.profile_wishlist_view, name="profile_wishlist"),
    path("profile/orders/", views.profile_orders_view, name="profile_orders"),
    path(
        "profile/verify/send/",
        views.send_verification_sms_view,
        name="send_verification_sms",
    ),
    path("profile/verify/confirm/", views.verify_sms_code_view, name="verify_sms_code"),
]
