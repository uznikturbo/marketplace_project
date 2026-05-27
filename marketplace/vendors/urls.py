from django.urls import path
from . import views

urlpatterns = [
    path("", views.vendor_view, name="vendor_view"),
    path("create_product/", views.create_product, name="create_product"),
    path("<int:pk>/update_product/", views.update_product, name="update_product"),
    path("<int:pk>/delete_product/", views.delete_product, name="delete_product"),
    path("<int:pk>/add_discount/", views.add_discount, name="add_discount"),
    path("orders/", views.vendor_orders_view, name="vendor_orders"),
    path("orders/<int:pk>/", views.vendor_order_detail, name="vendor_order_details"),
]
