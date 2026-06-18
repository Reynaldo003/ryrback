#Encuestas/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PublicEncuestaSatisfaccionCreateView,
    EncuestaSatisfaccionViewSet,
    PublicEncuestaServicioCreateView,
    EncuestaServicioViewSet,
    GenerarQRPermanenteView,
    QRInfoView,
    RespuestasEncuestaPorClienteView,
    EncuestaPisoViewSet,
)

router = DefaultRouter()
router.register(
    r"satisfaccion",
    EncuestaSatisfaccionViewSet,
    basename="encuestas-satisfaccion",
)
router.register(
    r"servicio",
    EncuestaServicioViewSet,
    basename="encuestas-servicio",
)
router.register(
    r"piso",
    EncuestaPisoViewSet,
    basename="encuestas-piso",
)

urlpatterns = [
    path(
        "public/encuestas/satisfaccion/",
        PublicEncuestaSatisfaccionCreateView.as_view(),
        name="public-encuesta-satisfaccion-create",
    ),
    path(
        "public/encuestas/servicio/",
        PublicEncuestaServicioCreateView.as_view(),
        name="public-encuesta-servicio-create",
    ),
    path("encuestas/", include(router.urls)),
    path("qr/info/", QRInfoView.as_view(), name="qr-info"),
    path("qr/generar-permanente/", GenerarQRPermanenteView.as_view(), name="qr-generar-permanente"),
    path("api/cliente/<int:cliente_id>/respuestas/",RespuestasEncuestaPorClienteView.as_view(),name="respuestas-por-cliente",),
]