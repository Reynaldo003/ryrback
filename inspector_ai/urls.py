#inspector_ai/urls.py
from django.urls import path

from .views import InspectorAnalizarView, InspectorCitasView

urlpatterns = [
    path("api/analizar/", InspectorAnalizarView.as_view(), name="inspector-ai-analizar"),
    path("api/citas/", InspectorCitasView.as_view(), name="inspector-ai-citas"),
]
