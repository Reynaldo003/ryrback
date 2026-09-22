# notificaciones/urls.py
from django.urls import path
from .views import (
    RegistrarTokenView,
    DiagnosticarNotificacionesView,
    ProbarNotificacionesView,
    ListadoNotificacionesView,
    ConteoNoLeidasView,
    MarcarLeidaView,
)

urlpatterns = [
    path('registrar-token/', RegistrarTokenView.as_view(), name='registrar-token'),
    path('diagnostico/', DiagnosticarNotificacionesView.as_view(), name='diagnostico-notificaciones'),
    path('probar/', ProbarNotificacionesView.as_view(), name='probar-notificaciones'),
    path('', ListadoNotificacionesView.as_view(), name='lista-notificaciones'),
    path('no-leidas/', ConteoNoLeidasView.as_view(), name='conteo-no-leidas'),
    path('marcar-leida/', MarcarLeidaView.as_view(), name='marcar-leida'),
]