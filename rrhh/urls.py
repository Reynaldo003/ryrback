from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    VacanteReclutamientoViewSet,
    PuestoViewSet,
    EvaluacionPuestoViewSet,
    ColaboradorViewSet,
)

router = DefaultRouter()

router.register(
    r"vacantes",
    VacanteReclutamientoViewSet,
    basename="rrhh-vacantes",
)

router.register(
    r"puestos",
    PuestoViewSet,
    basename="rrhh-puestos",
)

router.register(
    r"evaluaciones-puestos",
    EvaluacionPuestoViewSet,
    basename="rrhh-evaluaciones-puestos",
)

router.register(
    r"colaboradores",
    ColaboradorViewSet,
    basename="rrhh-colaboradores",
)

urlpatterns = [
    path("", include(router.urls)),
]