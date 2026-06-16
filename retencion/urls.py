from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OrdenServicioViewSet

router = DefaultRouter()
router.register(
    r"ordenes-servicio",
    OrdenServicioViewSet,
    basename="ordenes-servicio-retencion",
)

urlpatterns = [
    path("api/", include(router.urls)),
]