from django.urls import path
from .views import OrdenesFacturadasListView,OrdenFacturadaDetalleView,OrdenesFacturadasDashboardView,OrdenesFacturadasOpcionesView

app_name = "ordenes_facturadas"

urlpatterns = [
    path("api/",OrdenesFacturadasListView.as_view(),name="lista",),
    path("api/detalle/",OrdenFacturadaDetalleView.as_view(),name="detalle",),
    path("api/opciones/", OrdenesFacturadasOpcionesView.as_view(), name="opciones",),
]