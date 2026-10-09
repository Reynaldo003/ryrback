from django.urls import path

from .views import (
    GotaComentarioDetalleView,
    GotaComentarioListCreateView,
    GotaDashboardView,
    GotaObservacionesView,
    GotaOpcionesView,
    GotaOrdenesListView,
)

urlpatterns = [
    path("api/", GotaOrdenesListView.as_view(), name="gota-ordenes-list"),
    path("api/dashboard/", GotaDashboardView.as_view(), name="gota-dashboard"),
    path("api/opciones/", GotaOpcionesView.as_view(), name="gota-opciones"),
    path(
        "api/comentarios/",
        GotaComentarioListCreateView.as_view(),
        name="gota-comentarios",
    ),
    path(
        "api/comentarios/<int:pk>/",
        GotaComentarioDetalleView.as_view(),
        name="gota-comentario-detalle",
    ),
    path(
        "api/observaciones/",
        GotaObservacionesView.as_view(),
        name="gota-observaciones",
    ),
]
