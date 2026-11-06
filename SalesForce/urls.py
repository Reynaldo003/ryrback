from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ActividadProcesoViewSet, ActividadProspectoViewSet, EntregaComercialViewSet,
    FacturaComercialViewSet, ImportacionComercialViewSet, ProcesoComercialViewSet,
    ProcesoDetalleViewSet, ProspectoViewSet, TablasView,
)

router = DefaultRouter()
router.register(r"prospectos", ProspectoViewSet, basename="sf-prospectos")
router.register(r"procesos", ProcesoComercialViewSet, basename="sf-procesos")
router.register(r"procesos-detalle", ProcesoDetalleViewSet, basename="sf-procesos-detalle")
router.register(r"actividades-prospectos", ActividadProspectoViewSet, basename="sf-actividades-prospectos")
router.register(r"actividades-procesos", ActividadProcesoViewSet, basename="sf-actividades-procesos")
router.register(r"facturas", FacturaComercialViewSet, basename="sf-facturas")
router.register(r"entregas", EntregaComercialViewSet, basename="sf-entregas")
router.register(r"importaciones", ImportacionComercialViewSet, basename="sf-importaciones")

urlpatterns = [
    path("api/tablas/", TablasView.as_view(), name="sf-tablas"),
    path("api/", include(router.urls)),
]
