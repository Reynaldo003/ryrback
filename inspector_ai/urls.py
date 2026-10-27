#inspector_ai/urls.py
from django.urls import path

from .views import InspectorAnalizarView, InspectorCitasView, TarjetaViajeraPDFView

urlpatterns = [
    path("api/analizar/", InspectorAnalizarView.as_view(), name="inspector-ai-analizar"),
    path("api/citas/", InspectorCitasView.as_view(), name="inspector-ai-citas"),
    path("api/citas/<int:cita_id>/tarjeta-viajera/", TarjetaViajeraPDFView.as_view(), name="inspector-tarjeta-viajera",)
]
