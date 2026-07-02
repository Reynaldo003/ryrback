from django.urls import path
from .views import BitacoraCreateView, BitacoraListView

urlpatterns = [
    path("bitacoras/", BitacoraCreateView.as_view(), name="bitacora-create"),
    path("bitacoras/lista/", BitacoraListView.as_view(), name="bitacora-list"),
]