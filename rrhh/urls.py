# rrhh/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    VacanteReclutamientoViewSet,
    PuestoViewSet,
    EvaluacionPuestoViewSet,
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

urlpatterns = [
    path("", include(router.urls)),
]