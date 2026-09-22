from django.urls import path

from .views import (
    CompraRefaccionesDashboardView,
    CompraRefaccionesListView,
    CompraRefaccionesOpcionesView,
)


urlpatterns = [
    path(
        "api/",
        CompraRefaccionesListView.as_view(),
        name="compra-refacciones-list",
    ),

    path(
        "api/dashboard/",
        CompraRefaccionesDashboardView.as_view(),
        name="compra-refacciones-dashboard",
    ),

    path(
        "api/opciones/",
        CompraRefaccionesOpcionesView.as_view(),
        name="compra-refacciones-opciones",
    ),
]