from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("health", views.health_view, name="health"),
    path("health/", views.health_view),
    path("favicon.ico", views.favicon_view, name="favicon"),
]
