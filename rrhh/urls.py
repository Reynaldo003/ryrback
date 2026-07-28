from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    VacanteReclutamientoViewSet,
    PuestoViewSet,
    EvaluacionPuestoViewSet,
    ColaboradorViewSet,
    CategoriaAmbienteLaboralViewSet, 
    EvaluacionAmbienteLaboralViewSet, 
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

router.register(
    r"ambiente-laboral/categorias",
    CategoriaAmbienteLaboralViewSet,
    basename="rrhh-al-categorias",
)

router.register(
    r"ambiente-laboral/evaluaciones",
    EvaluacionAmbienteLaboralViewSet,
    basename="rrhh-al-evaluaciones",
)

urlpatterns = [
    path("", include(router.urls)),
]