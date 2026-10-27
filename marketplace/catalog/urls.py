from django.urls import path

from . import views

urlpatterns = [
    path("", views.catalog_view, name="catalog"),
    path("<int:pk>/detail/", views.product_detail_view, name="product_detail"),
    path("<int:pk>/submit_review/", views.submit_review, name="submit_review"),
    path("cart/add/<int:pk>/", views.cart_add, name="cart_add"),
    path("cart/remove/<int:pk>/", views.cart_remove, name="cart_remove"),
    path("cart/", views.cart_detail_view, name="cart_detail"),
    path("cart/update/<int:pk>/", views.cart_update, name="cart_update"),
    path("favorite/toggle/<int:pk>/", views.toggle_favorite, name="toggle_favorite"),
    path("wishlist", views.wishlist_view, name="wishlist_view"),
]
