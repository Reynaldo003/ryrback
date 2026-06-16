# jdpower/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EncuestaJDPowerViewSet, EncuestaJDPowerServicioViewSet

router = DefaultRouter()

router.register(
    r"encuestas",
    EncuestaJDPowerViewSet,
    basename="encuestas-jdpower",
)

#  SERVICIO  
router.register(
    r"encuestas-servicio",
    EncuestaJDPowerServicioViewSet,
    basename="encuestas-jdpower-servicio",
)

urlpatterns = [
    path("api/", include(router.urls)),
]