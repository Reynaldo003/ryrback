# flujo/urls.py

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DiagramaFlujoViewSet

router = DefaultRouter()

router.register(r"diagramas_flujo",DiagramaFlujoViewSet,basename="diagramas_flujo",)

urlpatterns = [
    path("", include(router.urls)),
]