from django.urls import path

from .views import (
    InventarioRefaccionesObsolescenciaDashboardView,
    InventarioRefaccionesObsolescenciaListView,
    InventarioRefaccionesObsolescenciaOpcionesView,
)


urlpatterns = [
    path("api/", InventarioRefaccionesObsolescenciaListView.as_view(), name="refacciones-obsolescencia-list",),
    path("api/dashboard/",InventarioRefaccionesObsolescenciaDashboardView.as_view(), name="refacciones-obsolescencia-dashboard",),
    path("api/opciones/",InventarioRefaccionesObsolescenciaOpcionesView.as_view(),name="refacciones-obsolescencia-opciones",),
]