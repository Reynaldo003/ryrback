from django.urls import path

from .views import (
    OrdenesFacturadasListView,
    OrdenesFacturadasOpcionesView,
)


urlpatterns = [
    path(
        "api/",
        OrdenesFacturadasListView.as_view(),
        name="ordenes-facturadas-list",
    ),

    path(
        "api/opciones/",
        OrdenesFacturadasOpcionesView.as_view(),
        name="ordenes-facturadas-opciones",
    ),
]