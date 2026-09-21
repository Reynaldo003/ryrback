from django.urls import path

from .views import (
    VWVNListView,
    VWVNDashboardView,
)

from .productos_estoque import ProductosEstoqueListView
from .inventario_refacciones import InventarioRefaccionesListView
from .compra_ref_tipificada import CompraRefTipificadaListView
from .compra_ref_graficos import CompraRefGraficosView
from .costo_venta import CostoVentaView
from .piezas_tipificadas import (
    PiezasJerarquiaListView,
    PiezasObsolescenciaListView,
    PiezasTipificadasListView,
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
    path(
        "api/piezas-tipificadas/obsolescencia/",
        PiezasObsolescenciaListView.as_view(),
        name="piezas-tipificadas-obsolescencia",
    ),
    path(
        "api/piezas-tipificadas/jerarquia/",
        PiezasJerarquiaListView.as_view(),
        name="piezas-tipificadas-jerarquia",
    ),
    path(
        "api/compra-ref-tipificada/graficos/",
        CompraRefGraficosView.as_view(),
        name="compra-ref-tipificada-graficos",
    ),
    path(
        "api/compra-ref-tipificada/",
        CompraRefTipificadaListView.as_view(),
        name="compra-ref-tipificada-list",
    ),
    path(
        "api/costo-venta/",
        CostoVentaView.as_view(),
        name="costo-venta",
    ),
]
#Actualizacion y prueba de venta de refacciones