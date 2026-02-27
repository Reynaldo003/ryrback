# citas/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CitasViewSet, CitasPisoViewSet, PruebasManejoViewSet

router = DefaultRouter()
router.register(r"citas", CitasViewSet, basename="citas")
router.register(r"citas-piso", CitasPisoViewSet, basename="citas-piso")
router.register(r"pruebas-manejo", PruebasManejoViewSet, basename="pruebas-manejo")

urlpatterns = [
    path("api/", include(router.urls)),
]