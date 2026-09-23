from django.urls import path

from .views import CompraRefaccionesListView,CompraRefaccionesOpcionesView,CompraRefaccionesPiezasView

urlpatterns = [
    path("api/",CompraRefaccionesListView.as_view(),name="compra-refacciones-list",),
    path("api/opciones/",CompraRefaccionesOpcionesView.as_view(),name="compra-refacciones-opciones",),
    path("api/piezas/",CompraRefaccionesPiezasView.as_view(),name="compra-refacciones-piezas",),
]