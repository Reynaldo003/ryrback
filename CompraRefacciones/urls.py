from django.urls import path

from .views import (
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
        "api/opciones/",
        CompraRefaccionesOpcionesView.as_view(),
        name="compra-refacciones-opciones",
    ),
]