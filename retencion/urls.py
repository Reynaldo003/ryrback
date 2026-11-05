#retencion/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OrdenServicioVentaViewSet, TareaClienteViewSet
from .views_postgres import OrdenServicioVentaPostgresViewSet

router = DefaultRouter()
router.register(r"ordenes-ventas",OrdenServicioVentaViewSet,basename="ordenes-ventas-retencion",)
router.register(r"tareas",TareaClienteViewSet,basename="tareas-retencion",)
router.register(
    "ordenes-ventas-postgres-prueba",
    OrdenServicioVentaPostgresViewSet,
    basename="ordenes-ventas-postgres-prueba",
)

urlpatterns = [
    path("api/", include(router.urls)),
]