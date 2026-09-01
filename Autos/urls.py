from django.urls import path

from .views import (
    VWVNListView,
    VWVNDashboardView,
)

urlpatterns = [
    path(
        "api/",
        VWVNListView.as_view(),
        name="ventas-vn-list",
    ),
    path(
        "api/dashboard/",
        VWVNDashboardView.as_view(),
        name="ventas-vn-dashboard",
    ),
]