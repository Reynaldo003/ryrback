#VentaRefacciones/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("api/", views.venta_refacciones_lista, name="venta-refacciones-lista"),
    path("api/opciones/", views.venta_refacciones_opciones, name="venta-refacciones-opciones"),
    path("api/piezas/", views.venta_refacciones_piezas, name="venta-refacciones-piezas"),
]
