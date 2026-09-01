from django.urls import path

from .views import VWVNListView


urlpatterns = [
    path(
        "api/",
        VWVNListView.as_view(),
        name="ventas-vn-list",
    ),
]