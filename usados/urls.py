#usados/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AvaluoUsadoViewSet

router = DefaultRouter()
router.register(r"avaluos", AvaluoUsadoViewSet, basename="avaluos")

urlpatterns = [
    path("api/", include(router.urls)),
]