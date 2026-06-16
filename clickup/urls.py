# clickup/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    EquipoViewSet,
    ProyectoViewSet,
    TableroViewSet,
    UsuarioSearchView,
    NotificacionViewSet,
    ReporteIncidenciaViewSet,
    ResumenIAView,  
)

router = DefaultRouter()
router.register(r"equipos", EquipoViewSet, basename="clickup-equipos")
router.register(r"notificaciones", NotificacionViewSet, basename="clickup-notificaciones")
router.register(r"reportes", ReporteIncidenciaViewSet, basename="clickup-reportes")

proyecto_list = ProyectoViewSet.as_view({"get": "list", "post": "create"})
proyecto_detail = ProyectoViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
proyecto_bootstrap = ProyectoViewSet.as_view({"post": "bootstrap"})

tablero_list = TableroViewSet.as_view({"get": "list"})
tablero_mover = TableroViewSet.as_view({"post": "mover_tarea"})
tablero_crear_tarea = TableroViewSet.as_view({"post": "crear_tarea"})
tablero_editar_tarea = TableroViewSet.as_view({"patch": "editar_tarea"})
tablero_eliminar_tarea = TableroViewSet.as_view({"delete": "eliminar_tarea"})
tablero_detalle_tarea = TableroViewSet.as_view({"get": "detalle_tarea"})
tablero_subir_evidencia = TableroViewSet.as_view({"post": "subir_evidencia"})

urlpatterns = [
    path("", include(router.urls)),
    path("usuarios/buscar/", UsuarioSearchView.as_view(), name="clickup-usuarios-buscar"),
    path("ia/resumen/", ResumenIAView.as_view(), name="clickup-ia-resumen"),

    path("equipos/<int:equipo_id>/proyectos/", proyecto_list, name="clickup-proyecto-list"),
    path("equipos/<int:equipo_id>/proyectos/<int:pk>/", proyecto_detail, name="clickup-proyecto-detail"),
    path("equipos/<int:equipo_id>/proyectos/<int:pk>/bootstrap/", proyecto_bootstrap, name="clickup-proyecto-bootstrap"),

    path("equipos/<int:equipo_id>/tablero/", tablero_list, name="clickup-tablero"),
    path("equipos/<int:equipo_id>/tablero/mover-tarea/", tablero_mover, name="clickup-mover-tarea"),
    path("equipos/<int:equipo_id>/tablero/crear-tarea/", tablero_crear_tarea, name="clickup-crear-tarea"),
    path("equipos/<int:equipo_id>/tablero/tareas/<int:tarea_id>/", tablero_editar_tarea, name="clickup-editar-tarea"),
    path("equipos/<int:equipo_id>/tablero/tareas/<int:tarea_id>/eliminar/", tablero_eliminar_tarea, name="clickup-eliminar-tarea"),
    path("equipos/<int:equipo_id>/tablero/tareas/<int:tarea_id>/detalle/", tablero_detalle_tarea, name="clickup-detalle-tarea"),
    path("equipos/<int:equipo_id>/tablero/tareas/<int:tarea_id>/evidencias/", tablero_subir_evidencia, name="clickup-subir-evidencia"),
]