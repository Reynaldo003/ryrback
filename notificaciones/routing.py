#notificaciones/routing.py
from django.urls import path

from .consumers import WhatsAppNotificacionesConsumer

websocket_urlpatterns = [
    path(
        "ws/notificaciones/whatsapp/",
        WhatsAppNotificacionesConsumer.as_asgi(),
    ),
]