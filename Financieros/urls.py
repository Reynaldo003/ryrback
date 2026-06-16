#Financieros/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import SolicitudCreditoViewSet, LongDriveViewSet

router = DefaultRouter()
router.register(r"solicitudes-credito", SolicitudCreditoViewSet, basename="solicitudes-credito")
router.register(r"long-drives", LongDriveViewSet, basename="long-drives")

urlpatterns = [
    path("api/", include(router.urls)),
]