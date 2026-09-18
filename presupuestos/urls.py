from django.urls import path

from .views import MatrizPresupuestosListView, MatrizPresupuestosRefListView, PresupuestosDashboardView, PresupuestosOpcionesView

urlpatterns = [
    path("api/",MatrizPresupuestosListView.as_view(),name="presupuestos-list",),
    path("api/refacciones/",MatrizPresupuestosRefListView.as_view(),name="presupuestos-refacciones-list",),
    path("api/dashboard/",PresupuestosDashboardView.as_view(),name="presupuestos-dashboard",),
    path("api/opciones/",PresupuestosOpcionesView.as_view(),name="presupuestos-opciones",),
]