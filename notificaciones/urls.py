# notificaciones/urls.py
from django.urls import path
from .views import (
    RegistrarTokenView,
    DiagnosticarNotificacionesView,
    ProbarNotificacionesView,
)

urlpatterns = [
    path('registrar-token/', RegistrarTokenView.as_view(), name='registrar-token'),
    path('diagnostico/', DiagnosticarNotificacionesView.as_view(), name='diagnostico-notificaciones'),
    path('probar/', ProbarNotificacionesView.as_view(), name='probar-notificaciones'),
]