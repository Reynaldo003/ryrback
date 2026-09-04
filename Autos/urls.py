from django.urls import path

from .views import (
    VWVNListView,
    VWVNDashboardView,
)

from .productos_estoque import ProductosEstoqueListView
from .inventario_refacciones import InventarioRefaccionesListView
from .piezas_tipificadas import PiezasTipificadasListView

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
    path(
    "api/productos/",
    ProductosEstoqueListView.as_view(),
    name="productos-estoque-list",
    ),
    path(
    "api/piezas/",
    InventarioRefaccionesListView.as_view(),
    name="inventario-refacciones-list",
),
    path(
    "api/piezas-tipificadas/",
    PiezasTipificadasListView.as_view(),
    name="piezas-tipificadas-list",
),
]