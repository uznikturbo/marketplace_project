from django.urls import path

from . import views
from .callbacks import liqpay_callback

urlpatterns = [
    path("checkout/", views.checkout, name="checkout"),
    path("api/np/cities/", views.np_get_cities, name="np_cities"),
    path("api/np/warehouses/", views.np_get_warehouses, name="np_warehouses"),
    path("liqpay-callback/", liqpay_callback, name="liqpay_callback"),
    path("order_success/<int:order_id>/", views.order_success, name="order_success"),
    path("order/<int:pk>/pay", views.order_pay, name="order_pay"),
]
