from django.urls import path

from .views import GotaDashboardView, GotaOrdenesListView, GotaOpcionesView

urlpatterns = [
    path("api/", GotaOrdenesListView.as_view(), name="gota-ordenes-list"),
    path("api/dashboard/", GotaDashboardView.as_view(), name="gota-dashboard"),
    path("api/opciones/", GotaOpcionesView.as_view(), name="gota-opciones"),
]
