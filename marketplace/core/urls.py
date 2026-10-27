from django.urls import path

from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("about/", views.info_page_view, {"slug": "about"}, name="about"),
    path("careers/", views.info_page_view, {"slug": "careers"}, name="careers"),
    path("news/", views.info_page_view, {"slug": "news"}, name="news"),
    path(
        "contacts/",
        views.info_page_view,
        {"slug": "contacts"},
        name="contacts",
    ),
    path(
        "how-to-order/",
        views.info_page_view,
        {"slug": "how-to-order"},
        name="how_to_order",
    ),
    path(
        "delivery/",
        views.info_page_view,
        {"slug": "delivery"},
        name="delivery",
    ),
    path(
        "warranty/",
        views.info_page_view,
        {"slug": "warranty"},
        name="warranty",
    ),
    path(
        "service-centers/",
        views.info_page_view,
        {"slug": "service-centers"},
        name="service_centers",
    ),
    path(
        "become-a-seller/",
        views.info_page_view,
        {"slug": "become-a-seller"},
        name="become_a_seller",
    ),
    path(
        "advertising/",
        views.info_page_view,
        {"slug": "advertising"},
        name="advertising",
    ),
    path(
        "affiliate/",
        views.info_page_view,
        {"slug": "affiliate"},
        name="affiliate",
    ),
    path(
        "support/",
        views.info_page_view,
        {"slug": "support"},
        name="support",
    ),
    path("health", views.health_view, name="health"),
    path("health/", views.health_view),
    path("favicon.ico", views.favicon_view, name="favicon"),
]
