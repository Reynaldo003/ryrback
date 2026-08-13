#retencion/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OrdenServicioVentaViewSet, TareaClienteViewSet

router = DefaultRouter()
router.register(
    r"ordenes-ventas",
    OrdenServicioVentaViewSet,
    basename="ordenes-ventas-retencion",
)
router.register(
    r"tareas",
    TareaClienteViewSet,
    basename="tareas-retencion",
)

urlpatterns = [
    path("api/", include(router.urls)),
]