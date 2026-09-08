from django.urls import path
from .views import InventarioRefaccionesObsolescenciaListView, InventarioRefaccionesObsolescenciaOpcionesView


urlpatterns = [
    path("api/", InventarioRefaccionesObsolescenciaListView.as_view(), name="refacciones-obsolescencia-list"),
    path("api/opciones/", InventarioRefaccionesObsolescenciaOpcionesView.as_view(), name="refacciones-obsolescencia-opciones"),
]