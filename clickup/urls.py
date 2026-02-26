# clickup/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import EquipoViewSet, ProyectoViewSet, TableroViewSet

router = DefaultRouter()
router.register(r"equipos", EquipoViewSet, basename="clickup-equipos")

proyecto_list = ProyectoViewSet.as_view({"get": "list", "post": "create"})
proyecto_detail = ProyectoViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
proyecto_bootstrap = ProyectoViewSet.as_view({"post": "bootstrap"})

tablero_list = TableroViewSet.as_view({"get": "list"})
tablero_mover = TableroViewSet.as_view({"post": "mover_tarea"})

urlpatterns = [
    path("", include(router.urls)),

    path("equipos/<int:equipo_id>/proyectos/", proyecto_list),
    path("equipos/<int:equipo_id>/proyectos/<int:pk>/", proyecto_detail),
    path("equipos/<int:equipo_id>/proyectos/<int:pk>/bootstrap/", proyecto_bootstrap),

    path("equipos/<int:equipo_id>/tablero/", tablero_list),
    path("equipos/<int:equipo_id>/tablero/mover-tarea/", tablero_mover),
]