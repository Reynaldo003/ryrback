# clickup/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TeamViewSet, ProjectViewSet, BoardViewSet

router = DefaultRouter()
router.register(r"teams", TeamViewSet, basename="clickup-teams")

project_list = ProjectViewSet.as_view({"get": "list", "post": "create"})
project_detail = ProjectViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
project_bootstrap = ProjectViewSet.as_view({"post": "bootstrap"})

board_list = BoardViewSet.as_view({"get": "list"})
board_move = BoardViewSet.as_view({"post": "move_task"})

urlpatterns = [
    path("", include(router.urls)),

    # proyectos por equipo
    path("teams/<int:team_id>/projects/", project_list),
    path("teams/<int:team_id>/projects/<int:pk>/", project_detail),
    path("teams/<int:team_id>/projects/<int:pk>/bootstrap/", project_bootstrap),

    # board
    path("teams/<int:team_id>/board/", board_list),
    path("teams/<int:team_id>/board/move-task/", board_move),
]