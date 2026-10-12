# logs/urls.py
from django.urls import path

from .views import LogCatalogoView, LogEstadoView, LogListView, LogResumenView

urlpatterns = [
    path("api/logs/", LogListView.as_view(), name="logs-lista"),
    path("api/logs/catalogo/", LogCatalogoView.as_view(), name="logs-catalogo"),
    path("api/logs/resumen/", LogResumenView.as_view(), name="logs-resumen"),
    path("api/logs/estado/", LogEstadoView.as_view(), name="logs-estado"),
]