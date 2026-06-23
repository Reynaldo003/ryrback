# inventario/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.get_inventario, name="get_inventario"),
    path("por-agencia/", views.get_inventario_por_agencia, name="get_inventario_por_agencia"),
    path("por-estatus/", views.get_inventario_por_estatus, name="get_inventario_por_estatus"),
    path("por-marca/", views.get_inventario_por_marca, name="get_inventario_por_marca"),
    path("nuevo-usado/", views.get_inventario_nuevo_usado, name="get_inventario_nuevo_usado"),
    path("nacional-importado/", views.get_inventario_nacional_importado, name="get_inventario_nacional_importado"),
    path("filtros/", views.get_inventario_filtros, name="get_inventario_filtros"),
]